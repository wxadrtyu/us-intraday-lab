"""First-crossing event trigger for the frozen four-factor hypothesis."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v42_multifactor_vol_target as v42
import evaluate_full_universe_intraday_v44_multihorizon_confirmation as v44
import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import search_full_universe_intraday_v15_prior5 as v15

from us_intraday_lab.fast_intraday_research import metrics

HORIZONS = ((17, 20, 23, 26), (20, 23, 26, 29), (17, 20, 23, 26, 29))
EXITS = (69, 72, 75)
WEIGHTINGS = ("equal", "reliability")
THRESHOLDS = (0.25, 0.50, 0.75, 1.0)
CONFIRMATIONS = (1, 2)
TARGETS = (0.25, 0.30, 0.35)
LOOKBACKS = (15, 20, 25)


def _observe(cube: v34.Cube, stream: v12.ReturnStream, full: bool = False):
    masks = cube.masks()
    names = (
        tuple(name for name, mask in masks.items() if mask.any())
        if full
        else v15.DEVELOPMENT_NAMES + ("development_oos_2024_2025",)
    )
    return {
        name: metrics(
            stream.values[masks[name]], stream.benchmark[masks[name]], stream.active[masks[name]]
        )
        for name in names
    }


def _score(cube: v34.Cube, model: v44.HorizonModel, exit_bar: int, weighting: str):
    specification = {
        "name": "event_trigger",
        "decision": model.decision,
        "exit": exit_bar,
        "assets": v44.ASSETS,
    }
    matrix, _, _ = v34._matrix(cube, specification, model.factors)
    weights = model.reliability.copy()
    if weighting == "equal":
        weights[:] = 1.0
    weights /= weights.sum()
    score = np.einsum(
        "saf,f,f->sa",
        (matrix - model.mean) / model.scale,
        model.direction,
        weights,
    )
    return np.where(np.isfinite(matrix).all(axis=2), score, -np.inf)


def _stream(
    cube: v34.Cube,
    models: list[v44.HorizonModel],
    exit_bar: int,
    weighting: str,
    threshold: float,
    confirmations: int,
    cost: float,
    delay: int,
    score_delta_floor: float | None = None,
):
    selected = np.full(len(cube.sessions), -1, dtype=int)
    entry = np.full(len(cube.sessions), -1, dtype=int)
    previous_asset = np.full(len(cube.sessions), -1, dtype=int)
    previous_above = np.zeros(len(cube.sessions), dtype=bool)
    previous_score = None
    assets = np.asarray(v44.ASSETS)
    for model in models:
        score = _score(cube, model, exit_bar, weighting)
        local = np.argmax(score, axis=1)
        best_asset = assets[local]
        best_score = score[cube.rows, local]
        above = np.isfinite(best_score) & (best_score >= threshold)
        trigger = (selected < 0) & above
        if score_delta_floor is not None:
            if previous_score is None:
                trigger[:] = False
            else:
                prior_for_asset = previous_score[cube.rows, local]
                delta_score = np.full(len(cube.sessions), np.nan)
                finite_delta = np.isfinite(best_score) & np.isfinite(prior_for_asset)
                np.subtract(
                    best_score,
                    prior_for_asset,
                    out=delta_score,
                    where=finite_delta,
                )
                trigger &= finite_delta & (delta_score >= score_delta_floor)
        if confirmations == 2:
            trigger &= previous_above & (previous_asset == best_asset)
        selected[trigger] = best_asset[trigger]
        entry[trigger] = model.decision + 1 + delay
        previous_asset = best_asset
        previous_above = above
        previous_score = score
    safe_asset = np.maximum(selected, 0)
    safe_entry = np.maximum(entry, 0)
    active = (selected >= 0) & (safe_entry < exit_bar)
    active &= (
        cube.first[cube.rows, safe_entry, safe_asset] <= safe_entry * 5 + cube.boundary_tolerance
    )
    active &= cube.first[cube.rows, exit_bar, safe_asset] <= exit_bar * 5 + cube.boundary_tolerance
    active &= np.isfinite(cube.opens[cube.rows, safe_entry, safe_asset])
    active &= np.isfinite(cube.opens[cube.rows, exit_bar, safe_asset])
    active &= np.isfinite(cube.opens[cube.rows, safe_entry, 0])
    active &= np.isfinite(cube.opens[:, exit_bar, 0])
    active &= cube.opens[cube.rows, safe_entry, safe_asset] > 0
    active &= cube.opens[cube.rows, safe_entry, 0] > 0
    values = np.zeros(len(cube.sessions))
    values[active] = (
        cube.opens[active, exit_bar, safe_asset[active]]
        / cube.opens[cube.rows[active], safe_entry[active], safe_asset[active]]
        - 1.0
        - cost
    )
    benchmark = np.zeros(len(cube.sessions))
    benchmark[active] = (
        cube.opens[active, exit_bar, 0] / cube.opens[cube.rows[active], safe_entry[active], 0] - 1.0
    )
    return v12.ReturnStream(values, benchmark, active, active.astype(int))


def _rank(standard: dict, cost: dict, delay: dict):
    return (
        min(float(standard[name]["annualized_return"]) for name in v15.DEVELOPMENT_NAMES),
        min(
            float(cost["development_oos_2024_2025"]["annualized_return"]),
            float(delay["development_oos_2024_2025"]["annualized_return"]),
        ),
        min(
            float(cost["development_oos_2024_2025"]["information_ratio"]),
            float(delay["development_oos_2024_2025"]["information_ratio"]),
        ),
    )


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = v34.Cube(args.root, "alpaca", 0)
    candidates = []
    planned = 0
    for horizons, exit_bar in itertools.product(HORIZONS, EXITS):
        models = v44._fit(development, horizons, exit_bar)
        if models is None:
            continue
        for weighting, threshold, confirmations, target, lookback in itertools.product(
            WEIGHTINGS, THRESHOLDS, CONFIRMATIONS, TARGETS, LOOKBACKS
        ):
            planned += 1
            raw = (
                _stream(
                    development,
                    models,
                    exit_bar,
                    weighting,
                    threshold,
                    confirmations,
                    v34.STANDARD_COST,
                    0,
                ),
                _stream(
                    development,
                    models,
                    exit_bar,
                    weighting,
                    threshold,
                    confirmations,
                    v34.STRESS_COST,
                    0,
                ),
                _stream(
                    development,
                    models,
                    exit_bar,
                    weighting,
                    threshold,
                    confirmations,
                    v34.STANDARD_COST,
                    1,
                ),
            )
            exposure = v42._exposure(raw[0].values, lookback, target, 0.0)
            streams = tuple(v42._scaled(stream, exposure) for stream in raw)
            observations = [_observe(development, stream) for stream in streams]
            definition = {
                "horizons": horizons,
                "exit": exit_bar,
                "weighting": weighting,
                "score_threshold": threshold,
                "confirmations": confirmations,
                "target_volatility": target,
                "lookback": lookback,
                "factors": v44.FACTORS,
            }
            candidates.append(
                (
                    _rank(*observations),
                    v12._identity(definition, "lev-v45e-"),
                    definition,
                    models,
                    streams,
                )
            )
    candidates.sort(key=lambda item: item[0], reverse=True)

    # Freeze the small event-trigger family before historical and 2026 diagnostics.
    historical = v34.Cube(args.root, "historical", 0)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    eligible = 0
    diagnostic_hits = 0
    for rank, candidate_id, definition, models, streams in candidates:
        standard, cost, delay = [_observe(development, stream, True) for stream in streams]
        historical_raw = _stream(
            historical,
            models,
            int(definition["exit"]),
            str(definition["weighting"]),
            float(definition["score_threshold"]),
            int(definition["confirmations"]),
            v34.STANDARD_COST,
            0,
        )
        historical_exposure = v42._exposure(
            historical_raw.values,
            int(definition["lookback"]),
            float(definition["target_volatility"]),
            0.0,
        )
        historical_obs = _observe(
            historical, v42._scaled(historical_raw, historical_exposure), True
        )["historical_2018_2020"]
        fold_obs = [
            metrics(streams[0].values[index], streams[0].benchmark[index], streams[0].active[index])
            for index in folds
        ]
        oos = standard["development_oos_2024_2025"]
        consumed = standard["consumed_2026_all"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        gates = {
            "standard_primary": v13._primary(standard),
            "cost_18bp_primary": v13._primary(cost),
            "delay_5min_primary": v13._primary(delay),
            "four_of_five_positive_folds": sum(
                float(item["annualized_return"]) > 0 for item in fold_obs
            )
            >= 4,
            "historical_positive_mdd_below_20pct": float(historical_obs["annualized_return"]) > 0
            and float(historical_obs["max_drawdown"]) < 0.20,
            "multiple_comparison_bonferroni_5pct": min(
                1.0, 2.0 * _normal_tail(abs(z_score)) * max(1, planned)
            )
            < 0.05,
            "consumed_2026_total_above_20pct": float(consumed["total_return"]) > 0.20,
            "consumed_2026_mdd_below_20pct": float(consumed["max_drawdown"]) < 0.20,
            "consumed_2026_ir_at_least_1": float(consumed["information_ratio"]) >= 1.0,
        }
        eligible += int(all(gates.values()))
        diagnostic_hits += int(
            gates["consumed_2026_total_above_20pct"]
            and gates["consumed_2026_mdd_below_20pct"]
            and gates["consumed_2026_ir_at_least_1"]
        )
        records.append(
            {
                "candidate_id": candidate_id,
                "definition": definition,
                "development_rank": list(rank),
                "standard": standard,
                "cost_18bp": cost,
                "delay_5min_9bp": delay,
                "historical_2018_2020": historical_obs,
                "folds": fold_obs,
                "gates": gates,
            }
        )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "small first-crossing family ranked on 2022-2025 only",
        "factor_version": v34.FACTOR_VERSION,
        "scan": {
            "planned_trials": planned,
            "evaluated_trials": len(candidates),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "diagnostic_hits": diagnostic_hits,
        "eligible": eligible,
        "records": records,
    }
    v12._atomic(args.output, payload)
    print(json.dumps({key: payload[key] for key in ("scan", "diagnostic_hits", "eligible")}))
    if records:
        best = records[0]
        print(
            json.dumps(
                {
                    "candidate_id": best["candidate_id"],
                    "definition": best["definition"],
                    "development_rank": best["development_rank"],
                    "oos": best["standard"]["development_oos_2024_2025"],
                    "cost_oos": best["cost_18bp"]["development_oos_2024_2025"],
                    "delay_oos": best["delay_5min_9bp"]["development_oos_2024_2025"],
                    "consumed_2026": best["standard"]["consumed_2026_all"],
                    "historical": best["historical_2018_2020"],
                    "gates": best["gates"],
                }
            )
        )


if __name__ == "__main__":
    main()
