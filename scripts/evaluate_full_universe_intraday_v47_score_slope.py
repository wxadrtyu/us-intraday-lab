"""Predeclared score-slope timing factor for the v45 event-trigger hypothesis."""

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
import evaluate_full_universe_intraday_v45_event_trigger_multifactor as v45
import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import search_full_universe_intraday_v15_prior5 as v15

from us_intraday_lab.fast_intraday_research import metrics

HORIZONS = ((20, 23, 26, 29),)
EXITS = (69, 72)
THRESHOLDS = (0.50, 0.75, 1.0)
SCORE_DELTA_FLOORS = (-0.10, 0.0, 0.10, 0.20)
CONFIRMATIONS = (1, 2)
TARGETS = (0.25, 0.30, 0.35)
LOOKBACKS = (15, 20)
WEIGHTING = "reliability"
WEAK_MARKET_2026_MIN_TOTAL_RETURN = 0.05


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


def _raw_streams(cube, models, definition):
    common = (
        cube,
        models,
        int(definition["exit"]),
        WEIGHTING,
        float(definition["score_threshold"]),
        int(definition["confirmations"]),
    )
    delta = float(definition["score_delta_floor"])
    return (
        v45._stream(*common, v34.STANDARD_COST, 0, score_delta_floor=delta),
        v45._stream(*common, v34.STRESS_COST, 0, score_delta_floor=delta),
        v45._stream(*common, v34.STANDARD_COST, 1, score_delta_floor=delta),
    )


def _scaled_streams(raw, definition):
    exposure = v42._exposure(
        raw[0].values,
        int(definition["lookback"]),
        float(definition["target_volatility"]),
        0.0,
    )
    return tuple(v42._scaled(stream, exposure) for stream in raw)


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
        for threshold, delta, confirmations, target, lookback in itertools.product(
            THRESHOLDS,
            SCORE_DELTA_FLOORS,
            CONFIRMATIONS,
            TARGETS,
            LOOKBACKS,
        ):
            planned += 1
            definition = {
                "horizons": horizons,
                "exit": exit_bar,
                "weighting": WEIGHTING,
                "score_threshold": threshold,
                "score_delta_floor": delta,
                "confirmations": confirmations,
                "target_volatility": target,
                "lookback": lookback,
                "factors": (*v44.FACTORS, "score_slope"),
            }
            streams = _scaled_streams(_raw_streams(development, models, definition), definition)
            observations = [_observe(development, stream) for stream in streams]
            candidates.append(
                (
                    _rank(*observations),
                    v12._identity(definition, "lev-v47s-"),
                    definition,
                    models,
                    streams,
                )
            )
    candidates.sort(key=lambda item: item[0], reverse=True)

    # The complete 288-cell family is frozen before old-history and 2026 diagnostics.
    historical = v34.Cube(args.root, "historical", 0)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    revised_gate_hits = 0
    for rank, candidate_id, definition, models, streams in candidates:
        standard, cost, delay = [_observe(development, stream, True) for stream in streams]
        historical_stream = _scaled_streams(
            _raw_streams(historical, models, definition), definition
        )[0]
        historical_obs = _observe(historical, historical_stream, True)["historical_2018_2020"]
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
        "selection_contract": "288-cell score-slope family ranked on 2022-2025 only",
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
