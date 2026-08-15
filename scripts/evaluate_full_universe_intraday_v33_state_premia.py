"""Predeclared shrinkage models for causal state-conditioned intraday premia."""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import search_full_universe_intraday_v15_prior5 as v15
import search_full_universe_intraday_v26_calendar_state as v26

from us_intraday_lab.fast_intraday_research import metrics

STANDARD_COST = 0.0009
STRESS_COST = 0.0018
SLEEVES = (
    {"name": "opening", "decision": 1, "exit": 15, "assets": (3, 4)},
    {"name": "morning", "decision": 17, "exit": 36, "assets": (1, 2, 3, 4)},
    {"name": "midday", "decision": 38, "exit": 56, "assets": tuple(range(1, 16))},
    {"name": "afternoon", "decision": 59, "exit": 77, "assets": (1, 2, 3, 4)},
)
CONFIGS = (
    {"alpha": 10.0, "quantile": 0.60},
    {"alpha": 10.0, "quantile": 0.75},
    {"alpha": 100.0, "quantile": 0.60},
    {"alpha": 100.0, "quantile": 0.75},
    {"alpha": 1000.0, "quantile": 0.60},
    {"alpha": 1000.0, "quantile": 0.75},
)


@dataclass(slots=True)
class Model:
    specification: dict[str, Any]
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    threshold: float


def _features(cube: v26.Cube, specification: dict[str, Any]):
    decision = int(specification["decision"])
    exit_bar = int(specification["exit"])
    entry = decision + 1
    assets = np.asarray(specification["assets"], dtype=int)
    observed = cube._features(decision)
    current = observed["current"][:, assets]
    recent = observed["recent"][:, assets]
    width = len(assets)
    weekday_angle = 2.0 * np.pi * cube.weekday / 5.0
    matrix = np.stack(
        [
            current,
            recent,
            current - observed["spy"][:, None],
            cube.gap[:, assets],
            cube.prior1[:, assets],
            cube.prior20[:, assets],
            np.repeat(cube.gap[:, 0, None], width, axis=1),
            np.repeat(cube.prior1[:, 0, None], width, axis=1),
            np.repeat(cube.prior20[:, 0, None], width, axis=1),
            np.repeat(np.sin(weekday_angle)[:, None], width, axis=1),
            np.repeat(np.cos(weekday_angle)[:, None], width, axis=1),
        ],
        axis=2,
    )
    tolerance = cube.boundary_tolerance
    quality = (
        (cube.first[:, entry, assets] <= entry * 5 + tolerance)
        & (cube.first[:, exit_bar, assets] <= exit_bar * 5 + tolerance)
        & (cube.first[:, entry, 0, None] <= entry * 5 + tolerance)
        & (cube.first[:, exit_bar, 0, None] <= exit_bar * 5 + tolerance)
    )
    label = cube.opens[:, exit_bar, assets] / cube.opens[:, entry, assets] - 1.0 - STANDARD_COST
    finite = np.isfinite(matrix).all(axis=2) & quality & np.isfinite(label)
    return matrix, label, finite


def _fit(cube: v26.Cube, config: dict[str, float]) -> list[Model]:
    masks = cube.masks()
    train = masks["train_2022_2023"]
    validation = masks["2024"]
    models = []
    for specification in SLEEVES:
        matrix, label, finite = _features(cube, specification)
        selected = train[:, None] & finite
        values = matrix[selected]
        target = label[selected]
        mean = values.mean(axis=0)
        scale = values.std(axis=0)
        scale[scale < 1e-8] = 1.0
        standardized = (values - mean) / scale
        coefficients = np.linalg.solve(
            standardized.T @ standardized + float(config["alpha"]) * np.eye(matrix.shape[2]),
            standardized.T @ target,
        )
        prediction = np.einsum("saf,f->sa", (matrix - mean) / scale, coefficients)
        prediction = np.where(finite, prediction, -np.inf)
        best = np.max(prediction, axis=1)
        threshold = float(
            np.quantile(best[validation & np.isfinite(best)], float(config["quantile"]))
        )
        models.append(Model(dict(specification), mean, scale, coefficients, threshold))
    return models


def _sleeve(cube: v26.Cube, model: Model, cost: float, delay: int) -> v12.ReturnStream:
    matrix, _, finite = _features(cube, model.specification)
    prediction = np.einsum("saf,f->sa", (matrix - model.mean) / model.scale, model.coefficients)
    prediction = np.where(finite, prediction, -np.inf)
    local = np.argmax(prediction, axis=1)
    assets = np.asarray(model.specification["assets"], dtype=int)
    selected = assets[local]
    score = prediction[cube.rows, local]
    entry = int(model.specification["decision"]) + 1 + delay
    exit_bar = int(model.specification["exit"])
    tolerance = cube.boundary_tolerance
    active = (
        np.isfinite(score)
        & (score >= model.threshold)
        & (cube.first[cube.rows, entry, selected] <= entry * 5 + tolerance)
        & (cube.first[cube.rows, exit_bar, selected] <= exit_bar * 5 + tolerance)
    )
    values = np.zeros(len(cube.sessions))
    values[active] = (
        cube.opens[active, exit_bar, selected[active]] / cube.opens[active, entry, selected[active]]
        - 1.0
        - cost
    )
    benchmark = np.where(active, cube.opens[:, exit_bar, 0] / cube.opens[:, entry, 0] - 1.0, 0.0)
    return v12.ReturnStream(values, benchmark, active, active.astype(int))


def _stream(cube: v26.Cube, models: list[Model], cost: float, delay: int):
    return v13._combine([_sleeve(cube, model, cost, delay) for model in models])


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = v26.Cube(args.root, "alpaca", 0)
    records = []
    model_sets: dict[str, list[Model]] = {}
    streams: dict[str, v12.ReturnStream] = {}
    for config in CONFIGS:
        candidate_id = v12._identity({"sleeves": SLEEVES, "config": config}, "lev-v33s-")
        models = _fit(development, config)
        model_sets[candidate_id] = models
        scenario_streams = {
            "standard": _stream(development, models, STANDARD_COST, 0),
            "cost_18bp": _stream(development, models, STRESS_COST, 0),
            "delay_5min_9bp": _stream(development, models, STANDARD_COST, 1),
        }
        streams[candidate_id] = scenario_streams["standard"]
        observations = {
            name: v13._observe(development, stream) for name, stream in scenario_streams.items()
        }
        records.append(
            {
                "candidate_id": candidate_id,
                "configuration": config,
                "development_rank": [
                    min(
                        float(observations["standard"][name]["annualized_return"])
                        for name in v15.DEVELOPMENT_NAMES
                    ),
                    float(
                        observations["cost_18bp"]["development_oos_2024_2025"]["annualized_return"]
                    ),
                    float(
                        observations["cost_18bp"]["development_oos_2024_2025"]["information_ratio"]
                    ),
                ],
                **observations,
            }
        )
    records.sort(key=lambda item: tuple(item["development_rank"]), reverse=True)

    historical = v26.Cube(args.root, "historical", 0)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    diagnostic_hits = 0
    eligible = 0
    for item in records:
        models = model_sets[item["candidate_id"]]
        historical_obs = v13._observe(historical, _stream(historical, models, STANDARD_COST, 0))
        standard_stream = streams[item["candidate_id"]]
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
        bonferroni = min(1.0, 2.0 * _normal_tail(abs(z_score)) * len(CONFIGS))
        gates = {
            "standard_primary": v15._primary(item["standard"]),
            "cost_18bp_primary": v15._primary(item["cost_18bp"]),
            "delay_5min_primary": v15._primary(item["delay_5min_9bp"]),
            "four_of_five_positive_folds": sum(
                float(fold["annualized_return"]) > 0 for fold in fold_obs
            )
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
        item["historical_cross_source"] = historical_obs
        item["development_folds"] = fold_obs
        item["multiple_comparison"] = {
            "total_trials": len(CONFIGS),
            "bonferroni_p": bonferroni,
        }
        item["gates"] = gates
        item["eligible_for_future_simulation_observation"] = all(gates.values())
        diagnostic_hits += int(gates["consumed_2026_total_above_20pct"])
        eligible += int(item["eligible_for_future_simulation_observation"])
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "ridge fit uses 2022-2023; 2024 sets thresholds; rank uses through 2025; 2026 attaches post-freeze",
        "execution_contract": "long-only; gross<=1; no overnight; four non-overlapping sleeves",
        "scan": {
            "predeclared_configurations": len(CONFIGS),
            "total_trials": len(CONFIGS),
            "frontier_size": len(records),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "diagnostic_2026_above_20_count": diagnostic_hits,
        "eligible_count": eligible,
        "frontier": records,
    }
    v12._atomic(args.output, payload)
    print(
        json.dumps(
            {"scan": payload["scan"], "diagnostic_hits": diagnostic_hits, "eligible": eligible}
        )
    )
    best = max(
        records, key=lambda item: float(item["standard"]["consumed_2026_all"]["total_return"])
    )
    print(
        json.dumps(
            {
                "candidate_id": best["candidate_id"],
                "configuration": best["configuration"],
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
