"""Predeclared prior-session market-regime overlays on frozen v20 candidates."""

from __future__ import annotations

import argparse
import heapq
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import search_full_universe_intraday_v15_prior5 as v15
import search_full_universe_intraday_v25_frozen_ensemble as v25

from us_intraday_lab.fast_intraday_research import metrics

REGIMES = {
    "bullish": {"return20_floor": 0.0, "vol20_ceiling": 0.02, "return1_floor": -0.02},
    "strong": {"return20_floor": 0.03, "vol20_ceiling": 0.025, "return1_floor": -0.03},
    "calm": {"return20_floor": -0.03, "vol20_ceiling": 0.015, "return1_floor": -0.01},
    "recovery": {"return20_floor": -0.05, "vol20_ceiling": 0.03, "return1_floor": 0.0},
}


def _states(cube) -> dict[str, np.ndarray]:
    exact = (cube.first[:, 0, 0] <= cube.boundary_tolerance) & (
        cube.last[:, 77, 0] >= 389 - cube.boundary_tolerance
    )
    daily = np.where(exact, cube.closes[:, 77, 0] / cube.opens[:, 0, 0] - 1.0, np.nan)
    prior1 = np.full(len(daily), np.nan)
    return20 = np.full(len(daily), np.nan)
    vol20 = np.full(len(daily), np.nan)
    prior1[1:] = daily[:-1]
    for index in range(20, len(daily)):
        window = daily[index - 20 : index]
        if np.isfinite(window).all():
            return20[index] = np.prod(1.0 + window) - 1.0
            vol20[index] = np.std(window, ddof=1)
    return {
        name: (
            (return20 >= float(p["return20_floor"]))
            & (vol20 <= float(p["vol20_ceiling"]))
            & (prior1 >= float(p["return1_floor"]))
        )
        for name, p in REGIMES.items()
    }


def _filter(stream: v12.ReturnStream, state: np.ndarray) -> v12.ReturnStream:
    active = stream.active & state
    return v12.ReturnStream(
        np.where(state, stream.values, 0.0),
        np.where(state, stream.benchmark, 0.0),
        active,
        np.where(state, stream.component_trades, 0),
    )


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sample-size", default=300, type=int)
    parser.add_argument("--frontier-size", default=300, type=int)
    args = parser.parse_args()
    started = time.perf_counter()
    artifact = (
        args.root
        / "artifacts"
        / "accelerated_research"
        / "full-universe-intraday-v20-unified-sources-exact.json"
    )
    records = v25._load(artifact, args.sample_size)
    development = v25.Source(args.root, "v20")
    states = _states(development.base)
    heap: list[tuple[tuple[float, float, float], int, dict[str, Any]]] = []
    serial = 0
    trials = 0
    for record in records:
        streams = {
            "standard": development.replay(record["specifications"], 0.0009, 0),
            "cost_18bp": development.replay(record["specifications"], 0.0018, 0),
            "delay_5min_9bp": development.replay(record["specifications"], 0.0009, 1),
        }
        for regime, state in states.items():
            observations = {
                name: v13._observe(development.base, _filter(stream, state))
                for name, stream in streams.items()
            }
            weakest = min(
                float(observations["standard"][name]["annualized_return"])
                for name in v15.DEVELOPMENT_NAMES
            )
            cost_oos = observations["cost_18bp"]["development_oos_2024_2025"]
            rank = (
                weakest,
                float(cost_oos["annualized_return"]),
                float(cost_oos["information_ratio"]),
            )
            item = {
                "base_candidate_id": record["candidate_id"],
                "specifications": record["specifications"],
                "regime": regime,
                "regime_parameters": REGIMES[regime],
                "development_rank": rank,
                **observations,
            }
            serial += 1
            trials += 1
            entry = (rank, serial, item)
            if len(heap) < args.frontier_size:
                heapq.heappush(heap, entry)
            elif rank > heap[0][0]:
                heapq.heapreplace(heap, entry)
    frontier = [item for _, _, item in sorted(heap, reverse=True)]

    historical = v25.Source(args.root, "v20", True)
    historical_states = _states(historical.base)
    masks = development.base.masks()
    folds = np.array_split(np.flatnonzero(masks["development_all"]), 5)
    diagnostic_hits = 0
    eligible = 0
    for item in frontier:
        regime = item["regime"]
        standard_stream = _filter(
            development.replay(item["specifications"], 0.0009, 0), states[regime]
        )
        historical_stream = _filter(
            historical.replay(item["specifications"], 0.0009, 0), historical_states[regime]
        )
        historical_obs = v13._observe(historical.base, historical_stream)
        fold_obs = [
            metrics(
                standard_stream.values[index],
                standard_stream.benchmark[index],
                standard_stream.active[index],
            )
            for index in folds
        ]
        oos = item["standard"]["development_oos_2024_2025"]
        consumed = item["standard"]["consumed_2026_all"]
        hist = historical_obs["historical_2018_2020"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * _normal_tail(abs(z_score)) * trials)
        gates = {
            "standard_primary": v15._primary(item["standard"]),
            "cost_18bp_primary": v15._primary(item["cost_18bp"]),
            "delay_5min_primary": v15._primary(item["delay_5min_9bp"]),
            "four_of_five_positive_folds": sum(float(x["annualized_return"]) > 0 for x in fold_obs)
            >= 4,
            "historical_positive_mdd_below_20pct": float(hist["annualized_return"]) > 0
            and float(hist["max_drawdown"]) < 0.20,
            "consumed_2026_total_above_20pct": float(consumed["total_return"]) > 0.20,
            "consumed_2026_mdd_below_20pct": float(consumed["max_drawdown"]) < 0.20,
            "consumed_2026_ir_at_least_1": float(consumed["information_ratio"]) >= 1.0,
            "multiple_comparison_bonferroni_5pct": bonferroni < 0.05,
            "start_date_stress_evaluated": False,
            "parameter_neighborhood_evaluated": False,
        }
        item["candidate_id"] = v12._identity(
            {"base": item["base_candidate_id"], "regime": regime}, "lev-v29r-"
        )
        item["historical_cross_source"] = historical_obs
        item["development_folds"] = fold_obs
        item["multiple_comparison"] = {"total_trials": trials, "bonferroni_p": bonferroni}
        item["gates"] = gates
        item["eligible_for_future_simulation_observation"] = all(gates.values())
        diagnostic_hits += int(gates["consumed_2026_total_above_20pct"])
        eligible += int(item["eligible_for_future_simulation_observation"])
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "v20 sample stratified over its development-ranked frozen frontier; four regimes predeclared and ranked on 2022-2025 only",
        "execution_contract": "long-only; gross<=1; no overnight; prior-session regime",
        "scan": {
            "sampled_base_candidates": len(records),
            "predeclared_regimes": len(REGIMES),
            "total_trials": trials,
            "frontier_size": len(frontier),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "diagnostic_2026_above_20_count": diagnostic_hits,
        "eligible_count": eligible,
        "frontier": frontier,
    }
    v12._atomic(args.output, payload)
    print(
        json.dumps(
            {"scan": payload["scan"], "diagnostic_hits": diagnostic_hits, "eligible": eligible}
        )
    )
    if frontier:
        best = max(
            frontier, key=lambda x: float(x["standard"]["consumed_2026_all"]["total_return"])
        )
        print(
            json.dumps(
                {
                    "candidate_id": best["candidate_id"],
                    "base_candidate_id": best["base_candidate_id"],
                    "regime": best["regime"],
                    "development_rank": best["development_rank"],
                    "oos": best["standard"]["development_oos_2024_2025"],
                    "cost_oos": best["cost_18bp"]["development_oos_2024_2025"],
                    "delay_oos": best["delay_5min_9bp"]["development_oos_2024_2025"],
                    "historical": best["historical_cross_source"]["historical_2018_2020"],
                    "consumed_2026": best["standard"]["consumed_2026_all"],
                    "gates": best["gates"],
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
