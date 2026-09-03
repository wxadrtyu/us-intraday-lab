"""Diversified top-k cross-sectional intraday residual-alpha portfolios."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v42_multifactor_vol_target as v42
import evaluate_full_universe_intraday_v47_score_slope as v47
import evaluate_full_universe_intraday_v4670_v5669_residual_alpha as residual
import numpy as np
import pandas as pd
from evaluate_full_universe_intraday_v1463_v1562_intraday_path_multifactor import (
    IntradayPathCube,
)

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 12009
LAST_VERSION = 12108
PRIOR_COMPARISON_CELLS = 312_183
ASSETS = np.arange(3, 16, dtype=int)
FACTOR_SETS = residual.FACTOR_SETS
SCHEDULES = residual.SCHEDULES
TOP_K = (2, 3, 4, 6)
QUANTILES = (0.0, 0.25, 0.50)
TARGETS = (0.25, 0.40)
ALPHA = 100.0
MECHANISM = "diversified_topk_cross_sectional_residual_alpha"


@dataclass(slots=True)
class Model:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray


def _identity(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _matrix(cube, factors, decision):
    available = cube.factors(decision)
    return np.stack([available[name][:, ASSETS] for name in factors], axis=2)


def _fit(cube, family, schedule):
    factors = FACTOR_SETS[family]
    decision, exit_bar = schedule
    entry = decision + 1
    matrix = _matrix(cube, factors, decision)
    asset_return = cube.opens[:, exit_bar, ASSETS] / cube.opens[:, entry, ASSETS] - 1.0
    spy_return = cube.opens[:, exit_bar, 0] / cube.opens[:, entry, 0] - 1.0
    target = asset_return - spy_return[:, None]
    quality = (cube.first[:, entry, ASSETS] <= entry * 5) & (
        cube.first[:, exit_bar, ASSETS] <= exit_bar * 5
    )
    train = cube.masks()["train_2022_2023"][:, None]
    finite = np.isfinite(matrix).all(axis=2) & np.isfinite(target) & quality
    values, labels = matrix[train & finite], target[train & finite]
    mean, scale = values.mean(axis=0), values.std(axis=0)
    scale[scale < 1e-8] = 1.0
    standardized = (values - mean) / scale
    coefficients = np.linalg.solve(
        standardized.T @ standardized + ALPHA * np.eye(len(factors)),
        standardized.T @ labels,
    )
    return Model(family, factors, decision, exit_bar, mean, scale, coefficients)


def _scores(cube, model):
    matrix = _matrix(cube, model.factors, model.decision)
    score = np.einsum(
        "saf,f->sa", (matrix - model.mean) / model.scale, model.coefficients
    )
    return np.where(np.isfinite(matrix).all(axis=2), score, -np.inf)


def _threshold(cube, score, top_k, quantile):
    ordered = np.partition(score, -top_k, axis=1)[:, -top_k:]
    aggregate = np.mean(ordered, axis=1)
    train = cube.masks()["train_2022_2023"] & np.isfinite(aggregate)
    return float(np.quantile(aggregate[train], quantile))


def _raw(cube, model, top_k, threshold, cost, delay):
    score = _scores(cube, model)
    selected = np.argpartition(score, -top_k, axis=1)[:, -top_k:]
    chosen = ASSETS[selected]
    chosen_score = np.take_along_axis(score, selected, axis=1)
    aggregate = np.mean(chosen_score, axis=1)
    entry = model.decision + 1 + delay
    exit_bar = model.exit_bar
    rows = np.arange(len(cube.sessions))[:, None]
    valid = np.isfinite(chosen_score).all(axis=1)
    valid &= (cube.first[rows, entry, chosen] <= entry * 5).all(axis=1)
    valid &= (cube.first[rows, exit_bar, chosen] <= exit_bar * 5).all(axis=1)
    valid &= np.isfinite(cube.opens[rows, entry, chosen]).all(axis=1)
    valid &= np.isfinite(cube.opens[rows, exit_bar, chosen]).all(axis=1)
    valid &= np.isfinite(cube.opens[:, entry, 0]) & np.isfinite(cube.opens[:, exit_bar, 0])
    active = valid & np.isfinite(aggregate) & (aggregate >= threshold)
    values = np.zeros(len(cube.sessions))
    portfolio_return = np.mean(
        cube.opens[rows, exit_bar, chosen] / cube.opens[rows, entry, chosen] - 1.0,
        axis=1,
    )
    values[active] = portfolio_return[active] - cost
    benchmark = np.zeros(len(cube.sessions))
    benchmark[active] = (
        cube.opens[active, exit_bar, 0] / cube.opens[active, entry, 0] - 1.0
    )
    return v34.v12.ReturnStream(
        values, benchmark, active, np.where(active, top_k, 0).astype(int)
    )


def _streams(cube, model, top_k, threshold, target):
    raw = tuple(
        _raw(cube, model, top_k, threshold, cost, delay)
        for cost, delay in (
            (v34.STANDARD_COST, 0),
            (v34.STRESS_COST, 0),
            (v34.STANDARD_COST, 1),
        )
    )
    exposure = v42._exposure(raw[0].values, 20, target, 0.0)
    return tuple(v42._scaled(stream, exposure) for stream in raw)


def _primary(observation):
    oos = observation["development_oos_2024_2025"]
    return (
        float(oos["annualized_return"]) >= 0.50
        and float(oos["max_drawdown"]) < 0.20
        and float(oos["information_ratio"]) >= 1.0
        and all(
            float(observation[name]["annualized_return"]) > 0
            for name in ("train_2022_2023", "2024", "2025")
        )
    )


def _rank(observations):
    return (
        min(x["development_oos_2024_2025"]["annualized_return"] for x in observations),
        min(x["development_oos_2024_2025"]["information_ratio"] for x in observations),
        -max(x["development_oos_2024_2025"]["max_drawdown"] for x in observations),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = IntradayPathCube(args.root, "alpaca", 0)
    historical = IntradayPathCube(args.root, "historical", 0)
    cells_by_version = {}
    version = FIRST_VERSION
    for family, schedule in itertools.product(FACTOR_SETS, SCHEDULES):
        model = _fit(development, family, schedule)
        score = _scores(development, model)
        cells = []
        for top_k, quantile, target in itertools.product(TOP_K, QUANTILES, TARGETS):
            threshold = _threshold(development, score, top_k, quantile)
            streams = _streams(development, model, top_k, threshold, target)
            observations = tuple(v47._observe(development, stream, True) for stream in streams)
            cells.append(
                {
                    "top_k": top_k,
                    "quantile": quantile,
                    "target": target,
                    "threshold": threshold,
                    "model": model,
                    "streams": streams,
                    "observations": observations,
                    "primary": all(_primary(item) for item in observations),
                    "rank": _rank(observations),
                }
            )
        cells_by_version[version] = cells
        version += 1
    total_cells = PRIOR_COMPARISON_CELLS + sum(map(len, cells_by_version.values()))
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    for version, cells in cells_by_version.items():
        selected = max(cells, key=lambda item: item["rank"])
        model = selected["model"]
        historical_streams = _streams(
            historical,
            model,
            selected["top_k"],
            selected["threshold"],
            selected["target"],
        )
        historical_obs = tuple(
            v47._observe(historical, stream, True)["historical_2018_2020"]
            for stream in historical_streams
        )
        streams, observations = selected["streams"], selected["observations"]
        fold_metrics = {
            name: [metrics(s.values[i], s.benchmark[i], s.active[i]) for i in folds]
            for name, s in zip(
                ("standard", "cost_18bp", "delay_5min_9bp"), streams, strict=True
            )
        }
        starts = {}
        for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
            mask = development.masks()["development_all"] & (
                development.dates >= pd.Timestamp(start)
            )
            starts[start] = {
                name: metrics(s.values[mask], s.benchmark[mask], s.active[mask])
                for name, s in zip(
                    ("standard", "cost_18bp", "delay_5min_9bp"), streams, strict=True
                )
            }
        k_i, q_i, t_i = (
            TOP_K.index(selected["top_k"]),
            QUANTILES.index(selected["quantile"]),
            TARGETS.index(selected["target"]),
        )
        neighbors = [
            item
            for item in cells
            if abs(TOP_K.index(item["top_k"]) - k_i)
            + abs(QUANTILES.index(item["quantile"]) - q_i)
            + abs(TARGETS.index(item["target"]) - t_i)
            <= 1
        ]
        neighborhood = sum(item["primary"] for item in neighbors) / len(neighbors)
        oos = observations[0]["development_oos_2024_2025"]
        z_score = float(oos["information_ratio"]) * math.sqrt(
            max(1, int(oos["trades"])) / 252
        )
        bonferroni = min(1.0, 2 * v47._normal_tail(abs(z_score)) * total_cells)
        gates = {
            "standard_primary": _primary(observations[0]),
            "cost_18bp_primary": _primary(observations[1]),
            "delay_5min_primary": _primary(observations[2]),
            "four_of_five_positive_folds_all_scenarios": all(
                sum(x["annualized_return"] > 0 for x in values) >= 4
                for values in fold_metrics.values()
            ),
            "all_start_dates_positive_all_scenarios": all(
                x["annualized_return"] > 0 for values in starts.values() for x in values.values()
            ),
            "historical_15pct_mdd_below_20pct_all_scenarios": all(
                x["annualized_return"] >= 0.15 and x["max_drawdown"] < 0.20
                for x in historical_obs
            ),
            "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
            "consumed_2026q1_above_5pct": observations[0]["consumed_2026q1"]["total_return"] > 0.05,
            "consumed_2026_total_above_5pct": observations[0]["consumed_2026_all"]["total_return"] > 0.05,
            "cumulative_bonferroni_5pct": bonferroni < 0.05,
        }
        definition = {
            "version": version,
            "mechanism": MECHANISM,
            "factor_set": model.family,
            "decision": model.decision,
            "exit": model.exit_bar,
            "top_k": selected["top_k"],
            "score_quantile": selected["quantile"],
            "target_volatility": selected["target"],
            "ridge_alpha": ALPHA,
            "gross_limit": 1.0,
        }
        records.append(
            {
                "candidate_id": f"lev-v{version}-" + _identity(definition),
                "definition": definition,
                "model": {
                    "factors": model.factors,
                    "mean": model.mean.tolist(),
                    "scale": model.scale.tolist(),
                    "coefficients": model.coefficients.tolist(),
                    "threshold": selected["threshold"],
                },
                "standard": observations[0],
                "cost_18bp": observations[1],
                "delay_5min_9bp": observations[2],
                "historical_scenarios": dict(
                    zip(("standard", "cost_18bp", "delay_5min_9bp"), historical_obs, strict=True)
                ),
                "development_folds": fold_metrics,
                "start_date_stress": starts,
                "neighbor_primary_share": neighborhood,
                "multiple_comparison": {
                    "total_cells": total_cells,
                    "z_score": z_score,
                    "bonferroni_p": bonferroni,
                },
                "gates": gates,
                "strict_pre_factory_null_pass": all(gates.values()),
            }
        )
    records.sort(
        key=lambda item: _rank(
            (item["standard"], item["cost_18bp"], item["delay_5min_9bp"])
        ),
        reverse=True,
    )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version_range": [FIRST_VERSION, LAST_VERSION],
        "versions": len(cells_by_version),
        "evaluated_cells": sum(map(len, cells_by_version.values())),
        "comparison_cells": total_cells,
        "strict_pre_factory_null_passes": sum(
            x["strict_pre_factory_null_pass"] for x in records
        ),
        "rejection_reason_counts": dict(
            Counter(k for x in records for k, passed in x["gates"].items() if not passed)
        ),
        "elapsed_seconds": time.perf_counter() - started,
        "records": records,
    }
    v34.v12._atomic(args.output, payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "versions": payload["versions"],
                "evaluated_cells": payload["evaluated_cells"],
                "strict_pre_factory_null_passes": payload["strict_pre_factory_null_passes"],
                "best": records[0]["candidate_id"],
                "elapsed_seconds": payload["elapsed_seconds"],
            }
        )
    )


if __name__ == "__main__":
    main()
