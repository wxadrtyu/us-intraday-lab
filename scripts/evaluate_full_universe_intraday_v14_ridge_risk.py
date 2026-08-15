"""Evaluate the development-frozen v14 ridge ensemble and causal risk controls.

Model fitting and candidate ranking use 2021-2025 only. Consumed 2026 and the
separate 2018-2020 source are attached only after the development frontier is
frozen.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import search_full_universe_intraday_v12_robustness as v12

from us_intraday_lab.fast_intraday_research import metrics

STANDARD_COST = 0.0009
STRESS_COST = 0.0018
DEVELOPMENT_NAMES = ("train_2022_2023", "2024", "2025")
V11_COST_OOS = 0.3544779208192217
V11_DELAY_OOS = 0.30288746336401373
FEATURE_COUNT = 10
RISK_GRIDS = {
    "stop": (0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.08),
    "fast": (5, 10, 20, 40),
    "slow": (20, 40, 60, 90),
    "fast_floor": (-0.10, -0.05, -0.025, 0.0, 0.025),
    "slow_floor": (-0.15, -0.10, -0.05, -0.025, 0.0),
    "defensive_weight": tuple(item / 10.0 for item in range(1, 10)),
}
BASE_SPECIFICATIONS = (
    {"decision": 2, "exit": 15, "universe": "leveraged", "alpha": 100.0, "quantile": 0.75},
    {"decision": 17, "exit": 42, "universe": "risk", "alpha": 100.0, "quantile": 0.65},
    {"decision": 47, "exit": 66, "universe": "leveraged", "alpha": 100.0, "quantile": 0.95},
    {"decision": 68, "exit": 77, "universe": "risk", "alpha": 100.0, "quantile": 0.95},
)
UNIVERSES = {"leveraged": np.arange(3, 5), "risk": np.arange(1, 5)}


@dataclass(slots=True)
class State:
    prior1: np.ndarray
    prior5: np.ndarray


@dataclass(slots=True)
class Model:
    specification: dict[str, Any]
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    threshold: float


@dataclass(slots=True)
class Stream:
    returns: np.ndarray
    benchmark: np.ndarray
    active: np.ndarray
    component_trades: np.ndarray


def _state(cube: v12.ResearchCube) -> State:
    tolerance = cube.boundary_tolerance
    exact = (cube.first[:, 0, :] <= tolerance) & (cube.last[:, 77, :] >= 389 - tolerance)
    daily = np.where(exact, cube.closes[:, 77, :] / cube.opens[:, 0, :] - 1.0, np.nan)
    prior1 = np.full_like(daily, np.nan)
    prior1[1:] = daily[:-1]
    prior5 = np.full_like(daily, np.nan)
    for index in range(5, len(cube.sessions)):
        window = daily[index - 5 : index]
        valid = np.isfinite(window).all(axis=0)
        prior5[index, valid] = np.prod(1.0 + window[:, valid], axis=0) - 1.0
    return State(prior1, prior5)


def _masks(cube: v12.ResearchCube) -> dict[str, np.ndarray]:
    output = cube.masks()
    if cube.source == "alpaca":
        years = cube.dates.year.to_numpy()
        output = {**output, "train_2022_2023": (years >= 2022) & (years <= 2023)}
    return output


def _features(
    cube: v12.ResearchCube, state: State, specification: dict[str, Any]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    decision = int(specification["decision"])
    exit_bar = int(specification["exit"])
    entry = decision + 1
    assets = UNIVERSES[str(specification["universe"])]
    feature = cube._features(decision)
    current = feature["current"]
    recent = feature["recent"]
    width = len(assets)
    matrix = np.stack(
        [
            current[:, assets],
            recent[:, assets],
            current[:, assets] - feature["spy"][:, None],
            state.prior1[:, assets],
            state.prior5[:, assets],
            np.repeat(feature["spy"][:, None], width, axis=1),
            np.repeat(feature["breadth"][:, None], width, axis=1),
            np.repeat(feature["dispersion"][:, None], width, axis=1),
            np.repeat(state.prior1[:, 0, None], width, axis=1),
            np.repeat(state.prior5[:, 0, None], width, axis=1),
        ],
        axis=2,
    )
    tolerance = cube.boundary_tolerance
    quality = (cube.first[:, entry, assets] <= entry * 5 + tolerance) & (
        cube.first[:, exit_bar, assets] <= exit_bar * 5 + tolerance
    )
    label = cube.opens[:, exit_bar, assets] / cube.opens[:, entry, assets] - 1.0 - STANDARD_COST
    finite = np.isfinite(matrix).all(axis=2) & quality & np.isfinite(label)
    return matrix, label, finite


def _fit_models(cube: v12.ResearchCube, state: State) -> list[Model]:
    train = _masks(cube)["train_2022_2023"]
    validation = _masks(cube)["2024"]
    models = []
    for specification in BASE_SPECIFICATIONS:
        matrix, label, finite = _features(cube, state, specification)
        selected = train[:, None] & finite
        values = matrix[selected]
        target = label[selected]
        mean = values.mean(axis=0)
        scale = values.std(axis=0)
        scale[scale < 1e-8] = 1.0
        standardized = (values - mean) / scale
        alpha = float(specification["alpha"])
        coefficients = np.linalg.solve(
            standardized.T @ standardized + alpha * np.eye(FEATURE_COUNT),
            standardized.T @ target,
        )
        predictions = np.einsum("saf,f->sa", (matrix - mean) / scale, coefficients)
        predictions = np.where(finite, predictions, -np.inf)
        best = np.max(predictions, axis=1)
        threshold = float(
            np.quantile(best[validation & np.isfinite(best)], specification["quantile"])
        )
        models.append(Model(dict(specification), mean, scale, coefficients, threshold))
    return models


def _score(cube: v12.ResearchCube, state: State, model: Model) -> tuple[np.ndarray, np.ndarray]:
    matrix, _, finite = _features(cube, state, model.specification)
    prediction = np.einsum("saf,f->sa", (matrix - model.mean) / model.scale, model.coefficients)
    prediction = np.where(finite, prediction, -np.inf)
    local = np.argmax(prediction, axis=1)
    assets = UNIVERSES[str(model.specification["universe"])]
    return assets[local], prediction[cube.rows, local]


def _sleeve(
    cube: v12.ResearchCube,
    state: State,
    model: Model,
    cost: float,
    delay: int,
    stop: float,
) -> Stream:
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
    return Stream(returns, benchmark, active, active.astype(int))


def _combine(streams: list[Stream]) -> Stream:
    return Stream(
        np.prod(1.0 + np.vstack([item.returns for item in streams]), axis=0) - 1.0,
        np.prod(1.0 + np.vstack([item.benchmark for item in streams]), axis=0) - 1.0,
        np.logical_or.reduce([item.active for item in streams]),
        np.vstack([item.component_trades for item in streams]).sum(axis=0),
    )


def _base_stream(
    cube: v12.ResearchCube,
    state: State,
    models: list[Model],
    cost: float,
    delay: int,
    stop: float,
) -> Stream:
    return _combine([_sleeve(cube, state, model, cost, delay, stop) for model in models])


def _trailing(values: np.ndarray, lookback: int) -> np.ndarray:
    output = np.full(len(values), np.nan)
    cumulative = np.concatenate(([0.0], np.cumsum(np.log1p(values))))
    for index in range(lookback, len(values)):
        output[index] = np.expm1(cumulative[index] - cumulative[index - lookback])
    return output


def _weighted(stream: Stream, weight: np.ndarray) -> Stream:
    return Stream(
        stream.returns * weight,
        stream.benchmark * weight,
        stream.active,
        stream.component_trades,
    )


def _observe(cube: v12.ResearchCube, stream: Stream) -> dict[str, dict[str, float | int]]:
    return {
        name: metrics(stream.returns[mask], stream.benchmark[mask], stream.active[mask])
        for name, mask in _masks(cube).items()
        if mask.any()
    }


def _primary(observations: dict[str, dict[str, float | int]]) -> bool:
    oos = observations["development_oos_2024_2025"]
    return (
        float(oos["annualized_return"]) >= 0.50
        and float(oos["max_drawdown"]) < 0.20
        and float(oos["information_ratio"]) >= 1.0
        and all(float(observations[name]["annualized_return"]) > 0 for name in DEVELOPMENT_NAMES)
    )


def _normal_tail(value: float) -> float:
    return 0.5 * math.erfc(value / math.sqrt(2.0))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--boundary-tolerance-minutes", choices=(0, 1), default=0, type=int)
    args = parser.parse_args()
    started = time.perf_counter()
    development = v12.ResearchCube(
        args.root, "alpaca", boundary_tolerance=args.boundary_tolerance_minutes
    )
    development_state = _state(development)
    models = _fit_models(development, development_state)
    scenarios: dict[float, tuple[Stream, Stream, Stream]] = {}
    records = []
    scanned = 0
    for stop in RISK_GRIDS["stop"]:
        standard = _base_stream(development, development_state, models, STANDARD_COST, 0, stop)
        cost = _base_stream(development, development_state, models, STRESS_COST, 0, stop)
        delay = _base_stream(development, development_state, models, STANDARD_COST, 1, stop)
        scenarios[stop] = (standard, cost, delay)
        trailing = {
            lookback: _trailing(standard.returns, lookback) for lookback in (5, 10, 20, 40, 60, 90)
        }
        for fast, slow, fast_floor, slow_floor, defensive_weight in itertools.product(
            RISK_GRIDS["fast"],
            RISK_GRIDS["slow"],
            RISK_GRIDS["fast_floor"],
            RISK_GRIDS["slow_floor"],
            RISK_GRIDS["defensive_weight"],
        ):
            if fast >= slow:
                continue
            scanned += 1
            good = (trailing[fast] >= fast_floor) & (trailing[slow] >= slow_floor)
            weight = np.where(good, 1.0, defensive_weight)
            observations = tuple(
                _observe(development, _weighted(item, weight)) for item in scenarios[stop]
            )
            weakest = min(
                float(observations[0][name]["annualized_return"]) for name in DEVELOPMENT_NAMES
            )
            stress_return = min(
                float(observations[1]["development_oos_2024_2025"]["annualized_return"]),
                float(observations[2]["development_oos_2024_2025"]["annualized_return"]),
            )
            stress_ir = min(
                float(observations[1]["development_oos_2024_2025"]["information_ratio"]),
                float(observations[2]["development_oos_2024_2025"]["information_ratio"]),
            )
            parameters = {
                "stop": stop,
                "fast": fast,
                "slow": slow,
                "fast_floor": fast_floor,
                "slow_floor": slow_floor,
                "defensive_weight": defensive_weight,
            }
            records.append(
                {
                    "candidate_id": v12._identity(
                        {"base": BASE_SPECIFICATIONS, "risk": parameters}, "lev-v14-"
                    ),
                    "parameters": parameters,
                    "development_rank": [weakest, stress_return, stress_ir],
                    "standard": observations[0],
                    "cost_18bp": observations[1],
                    "delay_5min_9bp": observations[2],
                }
            )
    records.sort(key=lambda item: tuple(item["development_rank"]), reverse=True)
    record_lookup = {
        tuple(item["parameters"][name] for name in RISK_GRIDS): item for item in records
    }
    retained = {item["candidate_id"]: item for item in records[:100]}
    retained.update({item["candidate_id"]: item for item in records if _primary(item["standard"])})
    frontier = sorted(
        retained.values(), key=lambda item: tuple(item["development_rank"]), reverse=True
    )
    # Development frontier is frozen before either diagnostic source is loaded.
    historical = v12.ResearchCube(
        args.root, "historical", boundary_tolerance=args.boundary_tolerance_minutes
    )
    historical_state = _state(historical)
    historical_scenarios = {
        stop: _base_stream(historical, historical_state, models, STANDARD_COST, 0, stop)
        for stop in scenarios
    }
    diagnostic_hits = 0
    eligible = 0
    development_mask = _masks(development)["development_all"]
    folds = np.array_split(np.flatnonzero(development_mask), 5)
    for item in frontier:
        p = item["parameters"]
        stop = float(p["stop"])
        standard, cost, delay = scenarios[stop]
        trailing = {
            int(p["fast"]): _trailing(standard.returns, int(p["fast"])),
            int(p["slow"]): _trailing(standard.returns, int(p["slow"])),
        }
        good = (trailing[int(p["fast"])] >= float(p["fast_floor"])) & (
            trailing[int(p["slow"])] >= float(p["slow_floor"])
        )
        weight = np.where(good, 1.0, float(p["defensive_weight"]))
        weighted_standard = _weighted(standard, weight)
        item["standard"] = _observe(development, weighted_standard)
        item["cost_18bp"] = _observe(development, _weighted(cost, weight))
        item["delay_5min_9bp"] = _observe(development, _weighted(delay, weight))
        historical_base = historical_scenarios[stop]
        historical_fast = _trailing(historical_base.returns, int(p["fast"]))
        historical_slow = _trailing(historical_base.returns, int(p["slow"]))
        historical_weight = np.where(
            (historical_fast >= float(p["fast_floor"]))
            & (historical_slow >= float(p["slow_floor"])),
            1.0,
            float(p["defensive_weight"]),
        )
        item["historical_cross_source"] = _observe(
            historical, _weighted(historical_base, historical_weight)
        )
        item["development_folds"] = [
            metrics(
                weighted_standard.returns[index],
                weighted_standard.benchmark[index],
                weighted_standard.active[index],
            )
            for index in folds
        ]
        item["start_date_stress"] = {
            start: metrics(
                weighted_standard.returns[
                    development_mask & (development.dates.to_numpy() >= np.datetime64(start))
                ],
                weighted_standard.benchmark[
                    development_mask & (development.dates.to_numpy() >= np.datetime64(start))
                ],
                weighted_standard.active[
                    development_mask & (development.dates.to_numpy() >= np.datetime64(start))
                ],
            )
            for start in ("2022-01-01", "2023-01-01", "2024-01-01")
        }
        neighbor_outcomes = []
        for name, grid in RISK_GRIDS.items():
            value = p[name]
            index = grid.index(value)
            for neighbor_index in (index - 1, index + 1):
                if not 0 <= neighbor_index < len(grid):
                    continue
                neighbor = dict(p)
                neighbor[name] = grid[neighbor_index]
                if int(neighbor["fast"]) >= int(neighbor["slow"]):
                    continue
                neighbor_record = record_lookup.get(tuple(neighbor[field] for field in RISK_GRIDS))
                if neighbor_record is not None:
                    neighbor_outcomes.append(_primary(neighbor_record["standard"]))
        item["parameter_neighborhood"] = {
            "count": len(neighbor_outcomes),
            "primary_pass_fraction": (
                sum(neighbor_outcomes) / len(neighbor_outcomes) if neighbor_outcomes else 0.0
            ),
        }
        consumed = item["standard"]["consumed_2026_all"]
        hist = item["historical_cross_source"]["historical_2018_2020"]
        cost_oos = item["cost_18bp"]["development_oos_2024_2025"]
        delay_oos = item["delay_5min_9bp"]["development_oos_2024_2025"]
        diagnostic_pass = (
            float(consumed["total_return"]) > 0.20
            and float(consumed["max_drawdown"]) < 0.20
            and float(consumed["information_ratio"]) >= 1.0
        )
        diagnostic_hits += int(diagnostic_pass)
        oos = item["standard"]["development_oos_2024_2025"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252.0)
        raw_p = 2.0 * _normal_tail(abs(z_score))
        item["multiple_comparison"] = {
            "raw_normal_p": raw_p,
            "bonferroni_p": min(1.0, raw_p * scanned),
            "trial_count": scanned,
        }
        gates = {
            "standard_primary": _primary(item["standard"]),
            "cost_improves_v11": float(cost_oos["annualized_return"]) > V11_COST_OOS,
            "delay_improves_v11": float(delay_oos["annualized_return"]) > V11_DELAY_OOS,
            "four_of_five_positive_folds": sum(
                float(fold["annualized_return"]) > 0 for fold in item["development_folds"]
            )
            >= 4,
            "parameter_neighborhood_70pct_primary": float(
                item["parameter_neighborhood"]["primary_pass_fraction"]
            )
            >= 0.70,
            "historical_positive_mdd_below_20pct": (
                float(hist["annualized_return"]) > 0 and float(hist["max_drawdown"]) < 0.20
            ),
            "consumed_2026_hard_diagnostic": diagnostic_pass,
            "multiple_comparison_bonferroni_5pct": raw_p * scanned < 0.05,
        }
        item["gates"] = gates
        item["eligible_for_future_simulation_observation"] = all(gates.values())
        eligible += int(item["eligible_for_future_simulation_observation"])
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": "base and risk frontier use 2021-2025 only; diagnostics post-freeze",
        "boundary_tolerance_minutes": args.boundary_tolerance_minutes,
        "datasets": {"alpaca": v12.ALPACA, "historical": v12.HISTORICAL},
        "base_specifications": BASE_SPECIFICATIONS,
        "scan": {
            "risk_cells": scanned,
            "frontier_size": len(frontier),
            "elapsed_seconds": time.perf_counter() - started,
        },
        "diagnostic_hit_count": diagnostic_hits,
        "standard_and_diagnostic_hit_count": sum(
            item["gates"]["standard_primary"] and item["gates"]["consumed_2026_hard_diagnostic"]
            for item in frontier
        ),
        "robustness_improvement_hit_count": sum(
            item["gates"]["standard_primary"]
            and item["gates"]["consumed_2026_hard_diagnostic"]
            and item["gates"]["cost_improves_v11"]
            and item["gates"]["delay_improves_v11"]
            for item in frontier
        ),
        "eligible_count": eligible,
        "frontier": frontier,
    }
    v12._atomic(args.output, payload)
    print(
        json.dumps(
            {
                "scan": payload["scan"],
                "diagnostic_hit_count": diagnostic_hits,
                "standard_and_diagnostic_hit_count": payload["standard_and_diagnostic_hit_count"],
                "robustness_improvement_hit_count": payload["robustness_improvement_hit_count"],
                "eligible_count": eligible,
            },
            sort_keys=True,
        )
    )
    hits = [
        item
        for item in frontier
        if item["gates"]["standard_primary"]
        and item["gates"]["consumed_2026_hard_diagnostic"]
        and item["gates"]["cost_improves_v11"]
        and item["gates"]["delay_improves_v11"]
    ]
    if hits:
        best = max(hits, key=lambda item: tuple(item["development_rank"]))
        print(
            json.dumps(
                {
                    "candidate_id": best["candidate_id"],
                    "parameters": best["parameters"],
                    "standard_oos": best["standard"]["development_oos_2024_2025"],
                    "cost_18bp_oos": best["cost_18bp"]["development_oos_2024_2025"],
                    "delay_oos": best["delay_5min_9bp"]["development_oos_2024_2025"],
                    "consumed_2026": best["standard"]["consumed_2026_all"],
                    "gates": best["gates"],
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
