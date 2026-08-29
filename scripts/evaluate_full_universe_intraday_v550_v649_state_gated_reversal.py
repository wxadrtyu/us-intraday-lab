"""Preregistered v550-v649 state-gated low-frequency reversal campaign."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from collections import Counter
from pathlib import Path

import evaluate_full_universe_intraday_v248_v347_mechanism_campaign as prior
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 550
LAST_VERSION = 649
PRIOR_COMPARISON_CELLS = 40_394
SCORE_QUANTILES = (0.30, 0.40, 0.50, 0.60)
CONFIRMATIONS = (1, 2)
TARGETS = (0.30, 0.35, 0.40, 0.45)
LOOKBACKS = (15, 25)
STATE_QUANTILES = (0.30, 0.50, 0.70)
STATE_FACTORS = {
    "spy_current": 1.0,
    "sector_breadth": 1.0,
    "risk_asset_agreement": 1.0,
    "spy_volatility": -1.0,
}
FAMILIES = (
    ("prior_weak_reversal", ("prior20_return", "recent_return", "close_location"), (-1, 1, 1)),
    ("prior_weak_vwap_reclaim", ("prior20_return", "vwap_distance", "close_location"), (-1, 1, 1)),
    ("gap_down_reclaim", ("gap", "recent_return", "close_location"), (-1, 1, 1)),
    ("intraday_dip_reclaim", ("current_return", "recent_return", "vwap_distance"), (-1, 1, 1)),
    ("residual_oversold_reclaim", ("leverage_residual", "recent_return", "close_location"), (-1, 1, 1)),
    ("flow_exhaustion_rebound", ("recent_return", "signed_volume_imbalance", "volume_acceleration"), (1, 1, -1)),
    ("compressed_laggard_rebound", ("prior20_return", "realized_volatility", "recent_return"), (-1, -1, 1)),
    ("relative_laggard_reclaim", ("relative_return", "recent_return", "path_efficiency"), (-1, 1, 1)),
    ("capitulation_stabilization", ("current_return", "recent_return", "volume_acceleration"), (-1, 1, -1)),
    ("rank_laggard_reclaim", ("current_rank", "recent_return", "close_location"), (-1, 1, 1)),
)
SCHEDULES = ((32, 53), (35, 65), (41, 65), (41, 72), (47, 75))
STATE_MODES = ("unfiltered", "orderly_rebound_cash_filter")
DEVELOPMENT_NAMES = ("train_2022_2023", "2024", "2025")
HISTORICAL_MIN_ANNUALIZED_RETURN = 0.0
REQUIRE_CONSUMED_2026Q1_GATE = False


def specifications() -> list[tuple]:
    return [
        (family, schedule, state_mode)
        for state_mode in STATE_MODES
        for schedule in SCHEDULES
        for family in FAMILIES
    ]


def _primary(observations: dict) -> bool:
    oos = observations["development_oos_2024_2025"]
    return (
        float(oos["annualized_return"]) >= 0.50
        and float(oos["max_drawdown"]) < 0.20
        and float(oos["information_ratio"]) >= 1.0
        and all(float(observations[name]["annualized_return"]) > 0 for name in DEVELOPMENT_NAMES)
    )


def _state_score(
    cube: prior.v53.Cube,
    decision: int,
    means: dict[str, float],
    scales: dict[str, float],
) -> np.ndarray:
    available = cube.factors(decision)
    pieces = [
        direction * (np.asarray(available[name][:, 0], dtype=float) - means[name]) / scales[name]
        for name, direction in STATE_FACTORS.items()
    ]
    return np.mean(np.stack(pieces, axis=1), axis=1)


def _fit_state(development: prior.v53.Cube, decision: int) -> tuple[dict[str, float], dict[str, float]]:
    train = development.masks()["train_2022_2023"]
    available = development.factors(decision)
    means = {
        name: float(np.nanmean(np.asarray(available[name][:, 0], dtype=float)[train]))
        for name in STATE_FACTORS
    }
    scales = {
        name: max(1e-8, float(np.nanstd(np.asarray(available[name][:, 0], dtype=float)[train])))
        for name in STATE_FACTORS
    }
    return means, scales


def _scale(raw: tuple[prior.v12.ReturnStream, ...], target: float, lookback: int) -> tuple[prior.v12.ReturnStream, ...]:
    exposure = prior.v42._exposure(raw[0].values, lookback, target, 0.0)
    return tuple(prior.v42._scaled(stream, exposure) for stream in raw)


def _cells(
    development: prior.v53.Cube,
    family: tuple[str, tuple[str, ...], tuple[int, ...]],
    schedule: tuple[int, int],
    state_mode: str,
) -> list[dict]:
    mechanism, factors, directions = family
    decision, exit_bar = schedule
    mean, scale = prior._fit_rule_stats(development, decision, factors)
    train = development.masks()["train_2022_2023"]
    base = {
        "mechanism": mechanism,
        "decision": decision,
        "exit": exit_bar,
        "factors": factors,
        "directions": directions,
    }
    score = prior._rule_score(development, decision, factors, directions, mean, scale)
    best = np.max(score, axis=1)
    threshold_values = best[train & np.isfinite(best)]
    state_means, state_scales = _fit_state(development, decision)
    state_score = _state_score(development, decision, state_means, state_scales)
    finite_state_train = state_score[train & np.isfinite(state_score)]
    state_options: tuple[float | None, ...] = (None,) if state_mode == "unfiltered" else STATE_QUANTILES
    cells = []
    for score_quantile, confirmations in itertools.product(SCORE_QUANTILES, CONFIRMATIONS):
        score_threshold = float(np.quantile(threshold_values, score_quantile))
        definition = {
            **base,
            "confirmations": confirmations,
        }
        raw = (
            prior._rule_raw(development, definition, mean, scale, score_threshold, prior.v34.STANDARD_COST, 0),
            prior._rule_raw(development, definition, mean, scale, score_threshold, prior.v34.STRESS_COST, 0),
            prior._rule_raw(development, definition, mean, scale, score_threshold, prior.v34.STANDARD_COST, 1),
        )
        for state_quantile in state_options:
            if state_quantile is None:
                allowed = np.ones(len(development.sessions), dtype=bool)
                state_threshold = None
            else:
                state_threshold = float(np.quantile(finite_state_train, state_quantile))
                allowed = np.isfinite(state_score) & (state_score >= state_threshold)
            masked = tuple(prior._mask_stream(stream, allowed) for stream in raw)
            for target, lookback in itertools.product(TARGETS, LOOKBACKS):
                streams = _scale(masked, target, lookback)
                observations = tuple(prior.v47._observe(development, stream) for stream in streams)
                parameters = {
                    **definition,
                    "state_mode": state_mode,
                    "score_quantile": score_quantile,
                    "score_threshold": score_threshold,
                    "state_quantile": state_quantile,
                    "state_threshold": state_threshold,
                    "target_volatility": target,
                    "lookback": lookback,
                }
                cells.append(
                    {
                        "parameters": parameters,
                        "model": {
                            "mean": mean.tolist(),
                            "scale": scale.tolist(),
                            "state_means": state_means,
                            "state_scales": state_scales,
                        },
                        "streams": streams,
                        "observations": observations,
                        "rank": prior.v47._rank(*observations),
                        "primary": all(_primary(item) for item in observations),
                    }
                )
    return cells


def _neighbor_share(cells: list[dict], selected: dict) -> float:
    chosen = selected["parameters"]
    axes = (SCORE_QUANTILES, CONFIRMATIONS, TARGETS, LOOKBACKS)
    selected_indexes = tuple(
        axis.index(chosen[name])
        for axis, name in zip(axes, ("score_quantile", "confirmations", "target_volatility", "lookback"), strict=True)
    )
    neighbors = []
    for cell in cells:
        parameters = cell["parameters"]
        if parameters["state_quantile"] != chosen["state_quantile"]:
            continue
        indexes = tuple(
            axis.index(parameters[name])
            for axis, name in zip(axes, ("score_quantile", "confirmations", "target_volatility", "lookback"), strict=True)
        )
        if sum(abs(left - right) for left, right in zip(selected_indexes, indexes, strict=True)) <= 1:
            neighbors.append(cell)
    return sum(item["primary"] for item in neighbors) / len(neighbors)


def _historical_stream(
    historical: prior.v53.Cube,
    selected: dict,
) -> prior.v12.ReturnStream:
    parameters = selected["parameters"]
    model = selected["model"]
    raw = prior._rule_raw(
        historical,
        parameters,
        np.asarray(model["mean"]),
        np.asarray(model["scale"]),
        float(parameters["score_threshold"]),
        prior.v34.STANDARD_COST,
        0,
    )
    if parameters["state_mode"] != "unfiltered":
        state_score = _state_score(
            historical,
            int(parameters["decision"]),
            model["state_means"],
            model["state_scales"],
        )
        raw = prior._mask_stream(
            raw,
            np.isfinite(state_score) & (state_score >= float(parameters["state_threshold"])),
        )
    return _scale((raw,), float(parameters["target_volatility"]), int(parameters["lookback"]))[0]


def _record(
    development: prior.v53.Cube,
    historical: prior.v53.Cube,
    version: int,
    cells: list[dict],
    selected: dict,
    total_cells: int,
) -> dict:
    standard, cost, delay = [prior.v47._observe(development, stream, True) for stream in selected["streams"]]
    historical_obs = prior.v47._observe(historical, _historical_stream(historical, selected), True)["historical_2018_2020"]
    folds = [
        metrics(selected["streams"][0].values[index], selected["streams"][0].benchmark[index], selected["streams"][0].active[index])
        for index in np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    ]
    starts = {}
    for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
        mask = development.masks()["development_all"] & (development.dates >= pd.Timestamp(start))
        starts[start] = metrics(
            selected["streams"][0].values[mask],
            selected["streams"][0].benchmark[mask],
            selected["streams"][0].active[mask],
        )
    neighborhood = _neighbor_share(cells, selected)
    oos = standard["development_oos_2024_2025"]
    z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
    bonferroni = min(1.0, 2.0 * prior.v47._normal_tail(abs(z_score)) * total_cells)
    gates = {
        "standard_primary": _primary(standard),
        "cost_18bp_primary": _primary(cost),
        "delay_5min_primary": _primary(delay),
        "four_of_five_positive_folds": sum(float(item["annualized_return"]) > 0 for item in folds) >= 4,
        "historical_return_floor_mdd_below_20pct": float(historical_obs["annualized_return"])
        >= HISTORICAL_MIN_ANNUALIZED_RETURN
        and float(historical_obs["max_drawdown"]) < 0.20,
        "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
        "consumed_2026_total_above_5pct": float(standard["consumed_2026_all"]["total_return"]) > 0.05,
        "cumulative_bonferroni_5pct": bonferroni < 0.05,
    }
    if REQUIRE_CONSUMED_2026Q1_GATE:
        gates["consumed_2026q1_above_5pct"] = (
            float(standard["consumed_2026q1"]["total_return"]) > 0.05
        )
    pre_null_names = tuple(name for name in gates if name != "cumulative_bonferroni_5pct")
    definition = {"version": version, **selected["parameters"]}
    return {
        "candidate_id": f"lev-v{version}-" + prior._identity(definition),
        "definition": definition,
        "model": selected["model"],
        "development_rank": list(selected["rank"]),
        "standard": standard,
        "cost_18bp": cost,
        "delay_5min_9bp": delay,
        "historical_2018_2020": historical_obs,
        "development_folds": folds,
        "start_date_stress": starts,
        "neighbor_primary_share": neighborhood,
        "multiple_comparison": {"total_cells": total_cells, "z_score": z_score, "bonferroni_p": bonferroni},
        "gates": gates,
        "pre_factory_null_pass": all(gates[name] for name in pre_null_names),
        "all_reference_gates_pass": all(gates.values()),
    }


def _failed(records: list[dict]) -> Counter[str]:
    return Counter(name for record in records for name, passed in record["gates"].items() if not passed)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = prior.v53.Cube(args.root, "alpaca", 0)
    historical = prior.v53.Cube(args.root, "historical", 0)
    specs = specifications()
    planned_cells = 50 * 64 + 50 * 192
    total_cells = PRIOR_COMPARISON_CELLS + planned_cells
    if len(specs) != 100 or planned_cells != 12_800:
        raise RuntimeError("V550_V649_PREREGISTRATION_MISMATCH")
    all_records = []
    versions = []
    for offset, (family, schedule, state_mode) in enumerate(specs):
        version = FIRST_VERSION + offset
        version_started = time.perf_counter()
        path = args.output_dir / f"full-universe-intraday-v{version}-exact.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            records = payload["records"]
        else:
            cells = _cells(development, family, schedule, state_mode)
            cells.sort(key=lambda item: item["rank"], reverse=True)
            records = [_record(development, historical, version, cells, item, total_cells) for item in cells[:3]]
            payload = {
                "schema_version": "1.0.0",
                "status": "COMPLETE",
                "version": version,
                "economic_hypothesis": f"{family[0]} over bars {schedule} with {state_mode}",
                "scan": {"evaluated_cells": len(cells), "frozen_frontier": 3, "elapsed_seconds": time.perf_counter() - version_started},
                "pre_factory_null_hits": sum(record["pre_factory_null_pass"] for record in records),
                "records": records,
            }
            prior.v12._atomic(path, payload)
        all_records.extend(records)
        versions.append({
            "version": version,
            "hypothesis": payload["economic_hypothesis"],
            "cells": payload["scan"]["evaluated_cells"],
            "pre_factory_null_hits": payload["pre_factory_null_hits"],
            "best_candidate_id": records[0]["candidate_id"],
            "best_oos_annualized_return": records[0]["standard"]["development_oos_2024_2025"]["annualized_return"],
            "best_consumed_2026_total_return": records[0]["standard"]["consumed_2026_all"]["total_return"],
        })
        summary = {
            "schema_version": "1.0.0",
            "status": "COMPLETE" if version == LAST_VERSION else "RUNNING",
            "version_range": [FIRST_VERSION, LAST_VERSION],
            "completed_versions": offset + 1,
            "planned_versions": 100,
            "planned_new_cells": planned_cells,
            "cumulative_comparison_cells": total_cells,
            "pre_factory_null_hits": sum(record["pre_factory_null_pass"] for record in all_records),
            "rejected_frontier_records": len(all_records) - sum(record["pre_factory_null_pass"] for record in all_records),
            "rejection_reason_counts": dict(_failed(all_records)),
            "elapsed_seconds": time.perf_counter() - started,
            "versions": versions,
        }
        prior.v12._atomic(args.summary, summary)
        print(json.dumps({"progress": f"{offset + 1}/100", **versions[-1]}), flush=True)


if __name__ == "__main__":
    main()
