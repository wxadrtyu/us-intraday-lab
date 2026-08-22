"""Harden the frozen v580 reversal component as a small v45 ensemble sleeve."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path
from typing import Any

import evaluate_full_universe_intraday_v248_v347_mechanism_campaign as prior
import evaluate_full_universe_intraday_v550_v649_state_gated_reversal as campaign
import numpy as np

from us_intraday_lab.fast_intraday_research import metrics

WEIGHTS = (0.05, 0.10, 0.15, 0.20)
TOTAL_COMPARISON_CELLS = 53_198


def _blend(
    anchor: prior.v12.ReturnStream, component: prior.v12.ReturnStream, weight: float
) -> prior.v12.ReturnStream:
    return prior.v12.ReturnStream(
        (1.0 - weight) * anchor.values + weight * component.values,
        (1.0 - weight) * anchor.benchmark + weight * component.benchmark,
        anchor.active | component.active,
        (1.0 - weight) * anchor.component_trades + weight * component.component_trades,
    )


def _component_streams(
    cube: prior.v53.Cube, definition: dict, model: dict
) -> tuple[prior.v12.ReturnStream, ...]:
    raw = tuple(
        prior._rule_raw(
            cube,
            definition,
            np.asarray(model["mean"]),
            np.asarray(model["scale"]),
            float(definition["score_threshold"]),
            cost,
            delay,
        )
        for cost, delay in (
            (prior.v34.STANDARD_COST, 0),
            (prior.v34.STRESS_COST, 0),
            (prior.v34.STANDARD_COST, 1),
        )
    )
    return campaign._scale(
        raw, float(definition["target_volatility"]), int(definition["lookback"])
    )


def _anchor_streams(
    cube: prior.v53.Cube, models: Any
) -> tuple[prior.v12.ReturnStream, ...]:
    raw = tuple(
        prior.v45._stream(cube, models, 72, "reliability", 0.75, 2, cost, delay)
        for cost, delay in (
            (prior.v34.STANDARD_COST, 0),
            (prior.v34.STRESS_COST, 0),
            (prior.v34.STANDARD_COST, 1),
        )
    )
    exposure = prior.v42._exposure(raw[0].values, 15, 0.35, 0.0)
    return tuple(prior.v42._scaled(stream, exposure) for stream in raw)


def _full_record(
    development: prior.v53.Cube,
    historical: prior.v53.Cube,
    definition: dict,
    model: dict,
    weight: float,
    anchor_models: Any,
) -> dict:
    component = _component_streams(development, definition, model)
    anchor = _anchor_streams(development, anchor_models)
    streams = tuple(_blend(left, right, weight) for left, right in zip(anchor, component, strict=True))
    observations = tuple(prior.v47._observe(development, stream, True) for stream in streams)
    historical_component = _component_streams(historical, definition, model)[0]
    historical_anchor = _anchor_streams(historical, anchor_models)[0]
    historical_obs = prior.v47._observe(
        historical, _blend(historical_anchor, historical_component, weight), True
    )["historical_2018_2020"]
    folds = [
        metrics(streams[0].values[index], streams[0].benchmark[index], streams[0].active[index])
        for index in np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    ]
    oos = observations[0]["development_oos_2024_2025"]
    z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
    return {
        "weight": weight,
        "standard": observations[0],
        "cost_18bp": observations[1],
        "delay_5min_9bp": observations[2],
        "historical_2018_2020": historical_obs,
        "folds": folds,
        "multiple_comparison": {
            "total_cells": TOTAL_COMPARISON_CELLS,
            "z_score": z_score,
            "bonferroni_p": min(
                1.0, 2.0 * prior.v47._normal_tail(abs(z_score)) * TOTAL_COMPARISON_CELLS
            ),
        },
        "streams": streams,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--component", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = prior.v53.Cube(args.root, "alpaca", 0)
    source = json.loads(args.component.read_text(encoding="utf-8"))
    component = source["records"][0]
    definition = component["definition"]
    model = component["model"]
    anchor_models = prior.v44._fit(development, (20, 23, 26, 29), 72)
    development_component = _component_streams(development, definition, model)
    development_anchor = _anchor_streams(development, anchor_models)
    frozen_weights = []
    for weight in WEIGHTS:
        observations = tuple(
            prior.v47._observe(development, _blend(anchor, sleeve, weight))
            for anchor, sleeve in zip(
                development_anchor, development_component, strict=True
            )
        )
        frozen_weights.append(
            (
                min(
                    float(item["development_oos_2024_2025"]["annualized_return"])
                    for item in observations
                ),
                weight,
            )
        )
    frozen_weights.sort(reverse=True)
    historical = prior.v53.Cube(args.root, "historical", 0)
    records = [
        _full_record(development, historical, definition, model, weight, anchor_models)
        for _, weight in frozen_weights
    ]
    for record in records:
        record["rank"] = min(
            float(record[name]["development_oos_2024_2025"]["annualized_return"])
            for name in ("standard", "cost_18bp", "delay_5min_9bp")
        )
    records.sort(key=lambda item: item["rank"], reverse=True)
    selected = records[0]
    standard = selected["standard"]
    cost = selected["cost_18bp"]
    delay = selected["delay_5min_9bp"]
    historical_obs = selected["historical_2018_2020"]
    gates = {
        "standard_primary": campaign._primary(standard),
        "cost_18bp_primary": campaign._primary(cost),
        "delay_5min_primary": campaign._primary(delay),
        "four_of_five_positive_folds": sum(
            float(item["annualized_return"]) > 0 for item in selected["folds"]
        )
        >= 4,
        "historical_positive_mdd_below_20pct": (
            float(historical_obs["annualized_return"]) > 0
            and float(historical_obs["max_drawdown"]) < 0.20
        ),
        "weight_neighborhood_primary": all(
            campaign._primary(record[scenario])
            for record in records
            for scenario in ("standard", "cost_18bp", "delay_5min_9bp")
        ),
        "consumed_2026_total_above_5pct": (
            float(standard["consumed_2026_all"]["total_return"]) > 0.05
        ),
        "cumulative_bonferroni_5pct": selected["multiple_comparison"]["bonferroni_p"] < 0.05,
    }
    clean_records = [
        {key: value for key, value in record.items() if key != "streams"} for record in records
    ]
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version": 650,
        "candidate_id": "lev-v650-reversal-component",
        "anchor_candidate_id": "lev-v45e-0d302fbf92727a31",
        "component_candidate_id": component["candidate_id"],
        "component_definition": definition,
        "component_model": model,
        "selected_component_weight": selected["weight"],
        "selected_anchor_weight": 1.0 - selected["weight"],
        "selection_contract": "four weights ranked on worst 2024-2025 execution stress before 2026 and historical attachment",
        "development_frozen_weight_order": [weight for _, weight in frozen_weights],
        "gates": gates,
        "pre_factory_null_pass": all(
            passed for name, passed in gates.items() if name != "cumulative_bonferroni_5pct"
        ),
        "records": clean_records,
        "elapsed_seconds": time.perf_counter() - started,
    }
    prior.v12._atomic(args.output, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
