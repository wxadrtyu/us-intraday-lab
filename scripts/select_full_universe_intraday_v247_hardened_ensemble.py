"""v247: development-only hardened selection from the frozen v238 weight family."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import analyze_full_universe_intraday_v53_cross_asset_factors as v53
import evaluate_full_universe_intraday_v44_multihorizon_confirmation as v44
import evaluate_full_universe_intraday_v47_score_slope as v47
import evaluate_full_universe_intraday_v146_v245_anchored_ensembles as v146
import numpy as np
import pandas as pd
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13

from us_intraday_lab.fast_intraday_research import metrics

COMPONENT_CANDIDATE_ID = "lev-v118-5d4329ecaa7a2114"
SOURCE_VERSION = 118
NEIGHBOR_WEIGHTS = (0.80, 0.85, 0.90, 0.95)


def _start_dates(cube: v53.Cube, stream: v12.ReturnStream) -> dict:
    development = cube.masks()["development_all"]
    return {
        start: metrics(
            stream.values[development & (cube.dates >= pd.Timestamp(start))],
            stream.benchmark[development & (cube.dates >= pd.Timestamp(start))],
            stream.active[development & (cube.dates >= pd.Timestamp(start))],
        )
        for start in ("2022-01-01", "2023-01-01", "2024-01-01")
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--component", required=True, type=Path)
    parser.add_argument("--component-null", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    source = json.loads(args.component.read_text(encoding="utf-8"))
    component = next(
        record for record in source["records"] if record["candidate_id"] == COMPONENT_CANDIDATE_ID
    )
    null_source = json.loads(args.component_null.read_text(encoding="utf-8"))
    null_result = next(
        item
        for item in null_source["results"]
        if item["component_candidate_id"] == COMPONENT_CANDIDATE_ID
    )["component_factory_null"]
    development = v53.Cube(args.root, "alpaca", 0)
    historical = v53.Cube(args.root, "historical", 0)
    anchor_models = v44._fit(development, (20, 23, 26, 29), 72)
    anchor_development = v146._v45_streams(development, anchor_models)
    anchor_historical = v146._v45_streams(historical, anchor_models)[0]
    component_development = v146._component_streams(development, component)
    component_historical = v146._component_streams(historical, component)[0]
    cells = []
    for weight in NEIGHBOR_WEIGHTS:
        streams = tuple(
            v146._blend(anchor, sleeve, weight)
            for anchor, sleeve in zip(anchor_development, component_development, strict=True)
        )
        observations = [v47._observe(development, stream, True) for stream in streams]
        primary = [v13._primary(observation) for observation in observations]
        minimum_oos_return = min(
            float(observation["development_oos_2024_2025"]["annualized_return"])
            for observation in observations
        )
        cells.append(
            {
                "v45_weight": weight,
                "component_weight": 1.0 - weight,
                "streams": streams,
                "observations": observations,
                "primary": primary,
                "development_rank": [sum(primary), minimum_oos_return],
            }
        )
    cells.sort(key=lambda item: tuple(item["development_rank"]), reverse=True)
    selected = cells[0]
    weight = float(selected["v45_weight"])
    historical_stream = v146._blend(anchor_historical, component_historical, weight)
    historical_observation = v47._observe(historical, historical_stream, True)[
        "historical_2018_2020"
    ]
    standard, cost, delay = selected["observations"]
    folds = [
        metrics(
            selected["streams"][0].values[index],
            selected["streams"][0].benchmark[index],
            selected["streams"][0].active[index],
        )
        for index in np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    ]
    neighborhood = [
        {
            "v45_weight": item["v45_weight"],
            "component_weight": item["component_weight"],
            "standard_primary": item["primary"][0],
            "cost_18bp_primary": item["primary"][1],
            "delay_5min_primary": item["primary"][2],
            "all_primary": all(item["primary"]),
            "standard_oos": item["observations"][0]["development_oos_2024_2025"],
            "cost_18bp_oos": item["observations"][1]["development_oos_2024_2025"],
            "delay_5min_oos": item["observations"][2]["development_oos_2024_2025"],
        }
        for item in cells
    ]
    gates = {
        "standard_primary": v13._primary(standard),
        "cost_18bp_primary": v13._primary(cost),
        "delay_5min_primary": v13._primary(delay),
        "four_of_five_positive_folds": (
            sum(float(item["annualized_return"]) > 0 for item in folds) >= 4
        ),
        "parameter_neighborhood_75pct_primary": (
            sum(item["all_primary"] for item in neighborhood) / len(neighborhood) >= 0.75
        ),
        "historical_positive_mdd_below_20pct": (
            float(historical_observation["annualized_return"]) > 0
            and float(historical_observation["max_drawdown"]) < 0.20
        ),
        "consumed_2026_total_above_5pct": (
            float(standard["consumed_2026_all"]["total_return"]) > 0.05
        ),
        "component_factory_null": bool(null_result["passed"]),
    }
    definition = {
        "version": 247,
        "strategy": "v45_anchored_flow_persistence_ensemble",
        "anchor_candidate_id": "lev-v45e-0d302fbf92727a31",
        "component_candidate_id": COMPONENT_CANDIDATE_ID,
        "component_definition": component["definition"],
        "v45_weight": weight,
        "component_weight": 1.0 - weight,
        "maximum_gross": 1.0,
    }
    oos = standard["development_oos_2024_2025"]
    z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
    cumulative_bonferroni_p = min(
        1.0,
        2.0 * v47._normal_tail(abs(z_score)) * v146.CUMULATIVE_COMPARISON_CELLS,
    )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version": 247,
        "candidate_id": "lev-v247-" + v146.campaign._identity(definition)[:16],
        "selection_contract": (
            "select the highest worst-case standard/cost/delay development return from the "
            "pre-existing v238 weight neighborhood before attaching historical or consumed-2026"
        ),
        "definition": definition,
        "standard": standard,
        "cost_18bp": cost,
        "delay_5min_9bp": delay,
        "historical_2018_2020": historical_observation,
        "development_folds": folds,
        "start_date_stress": _start_dates(development, selected["streams"][0]),
        "parameter_neighborhood": neighborhood,
        "component_factory_null": null_result,
        "multiple_comparison_pressure": {
            "reference": "cumulative two-sided Bonferroni",
            "cells": v146.CUMULATIVE_COMPARISON_CELLS,
            "z_score": z_score,
            "adjusted_p": cumulative_bonferroni_p,
            "passed": cumulative_bonferroni_p < 0.05,
            "interpretation": (
                "reported as a conservative reference; factory-native component null is the "
                "architecture-aligned marginal test"
            ),
        },
        "gates": gates,
        "economic_and_marginal_null_gates_passed": all(gates.values()),
        "inherited_exception": (
            "the 95-percent v45 anchor remains the user-authorized failed-null research-shadow "
            "exception; this record is not an independent full hard-gate pass"
        ),
        "elapsed_seconds": time.perf_counter() - started,
    }
    v12._atomic(args.output, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
