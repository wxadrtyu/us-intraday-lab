"""Small predeclared nonlinear cross-sectional models with post-freeze diagnostics."""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import evaluate_full_universe_intraday_v14_ridge_risk as v14
import numpy as np
import search_full_universe_intraday_v12_robustness as v12

from us_intraday_lab.fast_intraday_research import metrics

CONFIGS = (
    {"depth": 2, "min_leaf": 40, "quantile": 0.70, "trees": 64, "stop": 0.03},
    {"depth": 2, "min_leaf": 30, "quantile": 0.80, "trees": 64, "stop": 0.03},
    {"depth": 3, "min_leaf": 30, "quantile": 0.75, "trees": 64, "stop": 0.03},
    {"depth": 3, "min_leaf": 20, "quantile": 0.85, "trees": 64, "stop": 0.03},
)


@dataclass(slots=True)
class Node:
    value: float
    feature: int = -1
    threshold: float = 0.0
    left: Node | None = None
    right: Node | None = None


@dataclass(slots=True)
class Model:
    specification: dict[str, Any]
    trees: list[Node]
    threshold: float


def _fit_node(
    values: np.ndarray,
    target: np.ndarray,
    depth: int,
    min_leaf: int,
    generator: np.random.Generator,
) -> Node:
    node = Node(float(np.mean(target)))
    if depth == 0 or len(target) < 2 * min_leaf:
        return node
    best: tuple[float, int, float, np.ndarray] | None = None
    for feature in generator.choice(values.shape[1], size=min(4, values.shape[1]), replace=False):
        column = values[:, feature]
        for threshold in np.unique(np.quantile(column, (0.2, 0.4, 0.6, 0.8))):
            left = column <= threshold
            left_count = int(left.sum())
            if left_count < min_leaf or len(target) - left_count < min_leaf:
                continue
            loss = float(
                np.var(target[left]) * left_count
                + np.var(target[~left]) * (len(target) - left_count)
            )
            if best is None or loss < best[0]:
                best = (loss, int(feature), float(threshold), left)
    if best is None:
        return node
    _, node.feature, node.threshold, left = best
    node.left = _fit_node(values[left], target[left], depth - 1, min_leaf, generator)
    node.right = _fit_node(values[~left], target[~left], depth - 1, min_leaf, generator)
    return node


def _predict_node(node: Node, values: np.ndarray) -> np.ndarray:
    output = np.full(len(values), node.value)
    if node.feature < 0 or node.left is None or node.right is None:
        return output
    left = values[:, node.feature] <= node.threshold
    output[left] = _predict_node(node.left, values[left])
    output[~left] = _predict_node(node.right, values[~left])
    return output


def _predict(trees: list[Node], values: np.ndarray) -> np.ndarray:
    return np.mean(np.vstack([_predict_node(tree, values) for tree in trees]), axis=0)


def _fit_models(cube, state, config: dict[str, Any], seed: int) -> list[Model]:
    train = v14._masks(cube)["train_2022_2023"]
    validation = v14._masks(cube)["2024"]
    models = []
    for sleeve_index, specification in enumerate(v14.BASE_SPECIFICATIONS):
        matrix, label, finite = v14._features(cube, state, specification)
        selected = train[:, None] & finite
        values = matrix[selected]
        target = label[selected]
        generator = np.random.default_rng(seed + sleeve_index)
        trees = []
        for _ in range(int(config["trees"])):
            sample = generator.integers(0, len(target), size=len(target))
            trees.append(
                _fit_node(
                    values[sample],
                    target[sample],
                    int(config["depth"]),
                    int(config["min_leaf"]),
                    generator,
                )
            )
        prediction = _predict(trees, matrix.reshape(-1, matrix.shape[2])).reshape(label.shape)
        prediction = np.where(finite, prediction, -np.inf)
        best = np.max(prediction, axis=1)
        threshold = float(
            np.quantile(best[validation & np.isfinite(best)], float(config["quantile"]))
        )
        models.append(Model(dict(specification), trees, threshold))
    return models


def _score(cube, state, model: Model) -> tuple[np.ndarray, np.ndarray]:
    matrix, label, finite = v14._features(cube, state, model.specification)
    prediction = _predict(model.trees, matrix.reshape(-1, matrix.shape[2])).reshape(label.shape)
    prediction = np.where(finite, prediction, -np.inf)
    local = np.argmax(prediction, axis=1)
    assets = v14.UNIVERSES[str(model.specification["universe"])]
    return assets[local], prediction[cube.rows, local]


def _sleeve(cube, state, model: Model, cost: float, delay: int, stop: float) -> v14.Stream:
    decision = int(model.specification["decision"])
    scheduled_exit = int(model.specification["exit"])
    entry = decision + 1 + delay
    selected, score = _score(cube, state, model)
    tolerance = cube.boundary_tolerance
    active = (
        np.isfinite(score)
        & (score >= model.threshold)
        & (cube.first[cube.rows, entry, selected] <= entry * 5 + tolerance)
        & (cube.first[cube.rows, scheduled_exit, selected] <= scheduled_exit * 5 + tolerance)
    )
    exits = np.full(len(cube.sessions), scheduled_exit, dtype=int)
    for bar in range(entry + 1, scheduled_exit):
        signal_bar = bar - 1
        move = (
            cube.closes[cube.rows, signal_bar, selected] / cube.opens[cube.rows, entry, selected]
            - 1.0
        )
        hit = (
            active
            & (exits == scheduled_exit)
            & (cube.last[cube.rows, signal_bar, selected] >= signal_bar * 5 + 4 - tolerance)
            & (cube.first[cube.rows, bar, selected] <= bar * 5 + tolerance)
            & (move <= -stop)
        )
        exits[hit] = bar
    returns = np.zeros(len(cube.sessions))
    benchmark = np.zeros(len(cube.sessions))
    for bar in range(entry + 1, scheduled_exit + 1):
        mask = active & (exits == bar)
        returns[mask] = (
            cube.opens[mask, bar, selected[mask]] / cube.opens[mask, entry, selected[mask]]
            - 1.0
            - cost
        )
        benchmark[mask] = cube.opens[mask, bar, 0] / cube.opens[mask, entry, 0] - 1.0
    return v14.Stream(returns, benchmark, active, active.astype(int))


def _stream(cube, state, models: list[Model], cost: float, delay: int, stop: float) -> v14.Stream:
    return v14._combine([_sleeve(cube, state, model, cost, delay, stop) for model in models])


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = v12.ResearchCube(args.root, "alpaca", boundary_tolerance=0)
    state = v14._state(development)
    candidates = []
    model_sets = []
    for index, config in enumerate(CONFIGS):
        models = _fit_models(development, state, config, 20260815 + index * 100)
        model_sets.append(models)
        stop = float(config["stop"])
        streams = {
            "standard": _stream(development, state, models, v14.STANDARD_COST, 0, stop),
            "cost_18bp": _stream(development, state, models, v14.STRESS_COST, 0, stop),
            "delay_5min_9bp": _stream(development, state, models, v14.STANDARD_COST, 1, stop),
        }
        observations = {name: v14._observe(development, stream) for name, stream in streams.items()}
        candidates.append(
            {
                "candidate_id": v12._identity(config, "lev-v30x-"),
                "configuration": config,
                "development_rank": [
                    min(
                        float(observations["standard"][name]["annualized_return"])
                        for name in v14.DEVELOPMENT_NAMES
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
    candidates.sort(key=lambda x: tuple(x["development_rank"]), reverse=True)

    historical = v12.ResearchCube(args.root, "historical", boundary_tolerance=0)
    historical_state = v14._state(historical)
    development_mask = v14._masks(development)["development_all"]
    folds = np.array_split(np.flatnonzero(development_mask), 5)
    diagnostic_hits = 0
    eligible = 0
    for item, models in zip(
        candidates,
        [model_sets[CONFIGS.index(item["configuration"])] for item in candidates],
        strict=True,
    ):
        config = item["configuration"]
        standard_stream = _stream(
            development, state, models, v14.STANDARD_COST, 0, float(config["stop"])
        )
        historical_stream = _stream(
            historical, historical_state, models, v14.STANDARD_COST, 0, float(config["stop"])
        )
        historical_obs = v14._observe(historical, historical_stream)
        fold_obs = [
            metrics(
                standard_stream.returns[x], standard_stream.benchmark[x], standard_stream.active[x]
            )
            for x in folds
        ]
        oos = item["standard"]["development_oos_2024_2025"]
        consumed = item["standard"]["consumed_2026_all"]
        hist = historical_obs["historical_2018_2020"]
        z = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * _normal_tail(abs(z)) * len(CONFIGS))
        gates = {
            "standard_primary": v14._primary(item["standard"]),
            "cost_18bp_primary": v14._primary(item["cost_18bp"]),
            "delay_5min_primary": v14._primary(item["delay_5min_9bp"]),
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
        item["historical_cross_source"] = historical_obs
        item["development_folds"] = fold_obs
        item["multiple_comparison"] = {"total_trials": len(CONFIGS), "bonferroni_p": bonferroni}
        item["gates"] = gates
        item["eligible_for_future_simulation_observation"] = all(gates.values())
        diagnostic_hits += int(gates["consumed_2026_total_above_20pct"])
        eligible += int(item["eligible_for_future_simulation_observation"])
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "tree fitting uses 2022-2023; thresholds use 2024; candidate rank uses through 2025; 2026 attached post-freeze",
        "execution_contract": "long-only; gross<=1; no overnight; four non-overlapping sleeves",
        "scan": {
            "predeclared_model_configurations": len(CONFIGS),
            "total_trials": len(CONFIGS),
            "frontier_size": len(candidates),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "diagnostic_2026_above_20_count": diagnostic_hits,
        "eligible_count": eligible,
        "frontier": candidates,
    }
    v12._atomic(args.output, payload)
    print(
        json.dumps(
            {"scan": payload["scan"], "diagnostic_hits": diagnostic_hits, "eligible": eligible}
        )
    )
    best = max(candidates, key=lambda x: float(x["standard"]["consumed_2026_all"]["total_return"]))
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
