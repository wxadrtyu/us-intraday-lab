"""Freeze a development-ranked midday overlay, then attach consumed diagnostics.

The fixed base is the already-consumed v11 candidate. Consequently, even a
numerical pass here is diagnostic-only and cannot become an observation-pool
recommendation.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import search_full_universe_intraday_v15_prior5 as v15

from us_intraday_lab.fast_intraday_research import metrics

BASE = [
    {
        "family": "relative_strength_rotation",
        "parameters": {
            "slot": "opening",
            "decision": 2,
            "exit": 15,
            "universe": "all",
            "current_floor": 0.01,
            "relative_floor": 0.006,
            "prior_asset_floor": -0.10,
            "prior_spy_floor": -1.0,
            "spy_floor": 0.0,
        },
    },
    {
        "family": "relative_strength_rotation",
        "parameters": {
            "slot": "morning",
            "decision": 17,
            "exit": 42,
            "universe": "all",
            "current_floor": 0.02,
            "relative_floor": 0.0,
            "prior_asset_floor": -0.05,
            "prior_spy_floor": -1.0,
            "spy_floor": 0.0,
        },
    },
    {
        "family": "pullback_recovery_rotation",
        "parameters": {
            "slot": "afternoon",
            "decision": 53,
            "exit": 66,
            "universe": "all",
            "dip_ceiling": -0.015,
            "recovery_floor": -0.003,
            "prior_asset_floor": -0.10,
            "prior_spy_floor": -1.0,
            "spy_floor": -0.02,
        },
    },
    {
        "family": "pullback_recovery_rotation",
        "parameters": {
            "slot": "late",
            "decision": 71,
            "exit": 77,
            "universe": "risk",
            "dip_ceiling": -0.01,
            "recovery_floor": -0.003,
            "prior_asset_floor": 0.0,
            "prior_spy_floor": -1.0,
            "spy_floor": -0.02,
        },
    },
]
DEVELOPMENT_NAMES = v15.DEVELOPMENT_NAMES


def _observe(cube: v15.Cube, stream: v12.ReturnStream, names: tuple[str, ...]) -> dict[str, Any]:
    masks = cube.masks()
    return {
        name: metrics(
            stream.values[masks[name]], stream.benchmark[masks[name]], stream.active[masks[name]]
        )
        for name in names
    }


def _stream(
    cube: v15.Cube, specs: list[dict[str, Any]], cost: float, delay: int
) -> v12.ReturnStream:
    return v13._combine([cube.replay_spec(spec, cost, delay) for spec in specs])


def _rank(observations: dict[str, Any]) -> tuple[float, float, float]:
    return (
        min(float(observations[name]["annualized_return"]) for name in DEVELOPMENT_NAMES),
        float(observations["development_oos_2024_2025"]["annualized_return"]),
        float(observations["development_oos_2024_2025"]["information_ratio"]),
    )


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def _overlay_neighbors(overlay: dict[str, Any]):
    parameters = overlay["parameters"]
    for name, value in parameters.items():
        if name in {"slot", "universe"}:
            continue
        step = 1 if name in {"decision", "exit"} else max(abs(float(value)) * 0.20, 0.001)
        for alternative in (float(value) - step, float(value) + step):
            changed = {
                **parameters,
                name: int(alternative) if name in {"decision", "exit"} else alternative,
            }
            if 43 < changed["decision"] < changed["exit"] <= 54:
                yield {"family": overlay["family"], "parameters": changed}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--frontier-size", type=int, default=2000)
    args = parser.parse_args()
    started = time.perf_counter()
    cube = v15.Cube(args.root, "alpaca", 0)
    v15.SLOTS["midday"] = ((44, 47, 50), (50, 53))
    development_fields = DEVELOPMENT_NAMES + ("development_oos_2024_2025",)
    heap: list[tuple[tuple[float, float, float], int, dict[str, Any]]] = []
    scanned = 0
    serial = 0
    for overlay in v15._specifications("midday"):
        if int(overlay["parameters"]["exit"]) > 54:
            continue
        scanned += 1
        specifications = BASE + [overlay]
        standard = _stream(cube, specifications, 0.0009, 0)
        observations = _observe(cube, standard, development_fields)
        item = (_rank(observations), serial, overlay)
        serial += 1
        if len(heap) < args.frontier_size:
            heapq.heappush(heap, item)
        elif item[:2] > heap[0][:2]:
            heapq.heapreplace(heap, item)

    # The development frontier is frozen before any 2026 metric is calculated.
    frozen = sorted(heap, key=lambda item: (item[0], item[1]), reverse=True)
    diagnostic_hits: list[dict[str, Any]] = []
    diagnostic_fields = development_fields + (
        "consumed_2026q1",
        "consumed_2026_apr_aug",
        "consumed_2026_all",
    )
    for rank, _, overlay in frozen:
        specifications = BASE + [overlay]
        standard = _observe(cube, _stream(cube, specifications, 0.0009, 0), diagnostic_fields)
        if float(standard["consumed_2026_all"]["total_return"]) <= 0.20:
            continue
        cost = _observe(cube, _stream(cube, specifications, 0.0018, 0), diagnostic_fields)
        delay = _observe(cube, _stream(cube, specifications, 0.0009, 1), diagnostic_fields)
        diagnostic_hits.append(
            {
                "candidate_id": v12._identity(specifications, "lev-v16d-"),
                "development_rank": list(rank),
                "specifications": specifications,
                "standard": standard,
                "cost_18bp": cost,
                "delay_5min_9bp": delay,
            }
        )
    diagnostic_hits.sort(
        key=lambda item: float(item["standard"]["consumed_2026_all"]["total_return"]),
        reverse=True,
    )
    best = diagnostic_hits[0] if diagnostic_hits else None

    if best is not None:
        specifications = best["specifications"]
        standard_stream = _stream(cube, specifications, 0.0009, 0)
        development_positions = np.flatnonzero(cube.masks()["development_all"])
        best["development_folds"] = [
            metrics(
                standard_stream.values[index],
                standard_stream.benchmark[index],
                standard_stream.active[index],
            )
            for index in np.array_split(development_positions, 5)
        ]
        best["start_date_stress"] = {}
        for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
            mask = np.asarray(cube.dates >= pd.Timestamp(start)) & cube.masks()["development_all"]
            best["start_date_stress"][start] = metrics(
                standard_stream.values[mask],
                standard_stream.benchmark[mask],
                standard_stream.active[mask],
            )
        historical = v15.Cube(args.root, "historical", 0)
        best["historical_cross_source"] = v13._observe(
            historical, _stream(historical, specifications, 0.0009, 0)
        )
        dev_values = standard_stream.values[cube.masks()["development_all"]]
        deviation = float(np.std(dev_values, ddof=1))
        statistic = (
            float(np.mean(dev_values) / deviation * math.sqrt(len(dev_values)))
            if deviation
            else 0.0
        )
        best["multiple_comparison"] = {
            "total_trials": scanned,
            "t_statistic": statistic,
            "bonferroni_p": min(1.0, 2.0 * _normal_tail(abs(statistic)) * scanned),
        }
        neighborhood = []
        for neighbor in _overlay_neighbors(specifications[-1]):
            neighbor_specs = BASE + [neighbor]
            observation = _observe(
                cube,
                _stream(cube, neighbor_specs, 0.0009, 0),
                development_fields,
            )
            neighborhood.append(
                {
                    "overlay": neighbor,
                    "standard_primary": v15._primary(observation),
                    "observations": observation,
                }
            )
        best["parameter_neighborhood"] = {
            "count": len(neighborhood),
            "primary_pass_fraction": (
                sum(bool(item["standard_primary"]) for item in neighborhood) / len(neighborhood)
                if neighborhood
                else 0.0
            ),
            "outcomes": neighborhood,
        }
        standard = best["standard"]
        cost = best["cost_18bp"]
        delay = best["delay_5min_9bp"]
        best["gates"] = {
            "standard_primary": v15._primary(standard),
            "cost_18bp_primary": v15._primary(cost),
            "delay_5min_primary": v15._primary(delay),
            "four_of_five_positive_folds": sum(
                float(item["annualized_return"]) > 0 for item in best["development_folds"]
            )
            >= 4,
            "consumed_2026_total_above_20pct": float(standard["consumed_2026_all"]["total_return"])
            > 0.20,
            "consumed_2026_mdd_below_20pct": float(standard["consumed_2026_all"]["max_drawdown"])
            < 0.20,
            "consumed_2026_ir_at_least_1": float(standard["consumed_2026_all"]["information_ratio"])
            >= 1.0,
            "multiple_comparison_bonferroni_5pct": best["multiple_comparison"]["bonferroni_p"]
            < 0.05,
            "parameter_neighborhood_70pct_primary": (
                best["parameter_neighborhood"]["primary_pass_fraction"] >= 0.70
            ),
            "historical_cross_source_positive_mdd_below_20pct": (
                float(best["historical_cross_source"]["historical_2018_2020"]["annualized_return"])
                > 0
                and float(best["historical_cross_source"]["historical_2018_2020"]["max_drawdown"])
                < 0.20
            ),
            "independent_selection": False,
        }
        best["eligible_for_future_simulation_observation"] = all(best["gates"].values())

    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "midday overlay ranked on 2022-2025; fixed base was already selected using consumed 2026",
        "execution_contract": "long-only; gross<=1; no overnight; exact scheduled five-minute boundaries; five non-overlapping sleeves",
        "scan": {
            "cells": scanned,
            "frontier_size": len(frozen),
            "diagnostic_2026_above_20_count": len(diagnostic_hits),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "diagnostic_best": best,
        "eligible_count": int(
            best is not None and best["eligible_for_future_simulation_observation"]
        ),
    }
    v12._atomic(args.output, payload)
    print(json.dumps({"scan": payload["scan"], "eligible": payload["eligible_count"]}))
    if best:
        print(
            json.dumps(
                {
                    "candidate_id": best["candidate_id"],
                    "2026": best["standard"]["consumed_2026_all"],
                    "gates": best["gates"],
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
