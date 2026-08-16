"""Four-factor event trigger with equal holding length across signal times."""

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
import evaluate_full_universe_intraday_v47_score_slope as v47
import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import validate_full_universe_intraday_v46_factory_null as v46

from us_intraday_lab.fast_intraday_research import metrics

HORIZONS = (20, 23, 26, 29)
HOLDING_BARS = (36, 42)
THRESHOLDS = (0.50, 0.75, 1.0)
CONFIRMATIONS = (1, 2)
TARGETS = (0.25, 0.30, 0.35)
LOOKBACKS = (15, 20)
WEIGHTINGS = ("equal", "reliability")
WEAK_MARKET_2026_MIN_TOTAL_RETURN = 0.05


def _stream(cube: v34.Cube, models, definition: dict, cost: float, delay: int):
    selected, decision = v46._trigger(
        cube,
        models,
        72,
        str(definition["weighting"]),
        float(definition["score_threshold"]),
        int(definition["confirmations"]),
        None,
    )
    safe_asset = np.maximum(selected, 0)
    entry = decision + 1 + delay
    exit_bar = decision + 1 + int(definition["holding_bars"])
    safe_entry = np.maximum(entry, 0)
    safe_exit = np.clip(exit_bar, 0, 77)
    active = (selected >= 0) & (entry < exit_bar) & (exit_bar <= 77)
    active &= (
        cube.first[cube.rows, safe_entry, safe_asset] <= safe_entry * 5 + cube.boundary_tolerance
    )
    active &= (
        cube.first[cube.rows, safe_exit, safe_asset] <= safe_exit * 5 + cube.boundary_tolerance
    )
    active &= np.isfinite(cube.opens[cube.rows, safe_entry, safe_asset])
    active &= np.isfinite(cube.opens[cube.rows, safe_exit, safe_asset])
    active &= np.isfinite(cube.opens[cube.rows, safe_entry, 0])
    active &= np.isfinite(cube.opens[cube.rows, safe_exit, 0])
    active &= cube.opens[cube.rows, safe_entry, safe_asset] > 0
    active &= cube.opens[cube.rows, safe_entry, 0] > 0
    values = np.zeros(len(cube.sessions))
    values[active] = (
        cube.opens[cube.rows[active], safe_exit[active], safe_asset[active]]
        / cube.opens[cube.rows[active], safe_entry[active], safe_asset[active]]
        - 1.0
        - cost
    )
    benchmark = np.zeros(len(cube.sessions))
    benchmark[active] = (
        cube.opens[cube.rows[active], safe_exit[active], 0]
        / cube.opens[cube.rows[active], safe_entry[active], 0]
        - 1.0
    )
    return v12.ReturnStream(values, benchmark, active, active.astype(int))


def _scaled(cube, models, definition):
    raw = (
        _stream(cube, models, definition, v34.STANDARD_COST, 0),
        _stream(cube, models, definition, v34.STRESS_COST, 0),
        _stream(cube, models, definition, v34.STANDARD_COST, 1),
    )
    exposure = v42._exposure(
        raw[0].values,
        int(definition["lookback"]),
        float(definition["target_volatility"]),
        0.0,
    )
    return tuple(v42._scaled(stream, exposure) for stream in raw)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = v34.Cube(args.root, "alpaca", 0)
    models = v44._fit(development, HORIZONS, 72)
    if models is None:
        raise RuntimeError("frozen four-factor model did not fit")
    candidates = []
    planned = 0
    for holding, threshold, confirmations, target, lookback, weighting in itertools.product(
        HOLDING_BARS,
        THRESHOLDS,
        CONFIRMATIONS,
        TARGETS,
        LOOKBACKS,
        WEIGHTINGS,
    ):
        planned += 1
        definition = {
            "horizons": HORIZONS,
            "holding_bars": holding,
            "weighting": weighting,
            "score_threshold": threshold,
            "confirmations": confirmations,
            "target_volatility": target,
            "lookback": lookback,
            "factors": v44.FACTORS,
        }
        streams = _scaled(development, models, definition)
        observations = [v47._observe(development, stream) for stream in streams]
        candidates.append(
            (
                v47._rank(*observations),
                v12._identity(definition, "lev-v52h-"),
                definition,
                streams,
            )
        )
    candidates.sort(key=lambda item: item[0], reverse=True)

    # Freeze the 144-cell equal-holding family before diagnostics.
    historical = v34.Cube(args.root, "historical", 0)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    revised_gate_hits = 0
    for rank, candidate_id, definition, streams in candidates:
        standard, cost, delay = [v47._observe(development, stream, True) for stream in streams]
        historical_obs = v47._observe(historical, _scaled(historical, models, definition)[0], True)[
            "historical_2018_2020"
        ]
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
                1.0, 2.0 * v47._normal_tail(abs(z_score)) * max(1, planned)
            )
            < 0.05,
            "consumed_2026_total_above_5pct": float(consumed["total_return"])
            > WEAK_MARKET_2026_MIN_TOTAL_RETURN,
        }
        revised_gate_hits += int(
            all(
                gates[name]
                for name in (
                    "standard_primary",
                    "cost_18bp_primary",
                    "delay_5min_primary",
                    "four_of_five_positive_folds",
                    "historical_positive_mdd_below_20pct",
                    "consumed_2026_total_above_5pct",
                )
            )
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
        "selection_contract": (
            "equal holding length removes fixed-exit duration bias; the 144-cell family was "
            "frozen before diagnostics"
        ),
        "revised_2026_gate": {
            "metric": "consumed_2026_all.total_return",
            "operator": ">",
            "threshold": WEAK_MARKET_2026_MIN_TOTAL_RETURN,
        },
        "scan": {
            "planned_trials": planned,
            "evaluated_trials": len(candidates),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "revised_gate_hits_before_factory_null": revised_gate_hits,
        "records": records,
    }
    v12._atomic(args.output, payload)
    print(
        json.dumps(
            {
                "scan": payload["scan"],
                "revised_gate_hits_before_factory_null": revised_gate_hits,
            }
        )
    )
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
