"""Preregistered multifactor residual-alpha campaign targeting excess-return IR."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v42_multifactor_vol_target as v42
import evaluate_full_universe_intraday_v47_score_slope as v47
import numpy as np
import pandas as pd
from evaluate_full_universe_intraday_v1463_v1562_intraday_path_multifactor import IntradayPathCube

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 4670
LAST_VERSION = 5669
PRIOR_COMPARISON_CELLS = 253_305
ASSETS = np.asarray((3, 4), dtype=int)
SCHEDULES = ((2, 23), (5, 29), (8, 35), (11, 47), (17, 53), (23, 59), (29, 65), (35, 71), (41, 72), (47, 77))
QUANTILES = (0.30, 0.40, 0.50, 0.60, 0.70)
ALPHAS = (10.0, 1000.0)
FACTOR_SETS = {
    "trend_flow_state": ("current_return", "recent_return", "relative_return", "path_efficiency", "signed_volume_imbalance", "volume_acceleration", "prior1_return", "prior20_return", "spy_prior20", "spy_volatility"),
    "trend_structure": ("current_return", "recent_return", "relative_return", "path_efficiency", "vwap_distance", "close_location", "range_ratio", "session_range"),
    "cross_persistence": ("current_return", "relative_return", "current_rank", "prior20_rank", "prior1_return", "prior20_return", "sector_breadth"),
    "reclaim_flow": ("drawdown_from_high", "rebound_from_low", "return_acceleration", "vwap_distance", "close_location", "signed_volume_imbalance"),
    "contraction_breakout": ("recent_volatility_ratio", "recent_volume_ratio", "current_return", "return_acceleration", "path_efficiency", "intraday_range_position"),
    "failed_breakdown": ("drawdown_from_high", "rebound_from_low", "intraday_range_position", "return_acceleration", "relative_return"),
    "relative_leadership": ("relative_return", "current_rank", "prior20_rank", "path_efficiency", "signed_volume_imbalance", "close_location"),
    "gap_repair": ("gap", "current_return", "relative_return", "rebound_from_low", "return_acceleration", "spy_prior20"),
    "volatility_flow": ("realized_volatility", "session_range", "recent_volatility_ratio", "signed_volume_imbalance", "volume_acceleration", "spy_volatility"),
    "balanced_path": ("current_return", "relative_return", "path_efficiency", "signed_volume_imbalance", "vwap_distance", "close_location", "drawdown_from_high", "rebound_from_low", "return_acceleration", "prior20_return", "spy_volatility"),
}


@dataclass(slots=True)
class Model:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    quantile: float
    alpha: float
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    threshold: float


def specifications():
    return list(itertools.product(FACTOR_SETS, SCHEDULES, QUANTILES, ALPHAS))


def _identity(definition):
    encoded = json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _matrix(cube, factors, decision):
    available = cube.factors(decision)
    return np.stack([available[name][:, ASSETS] for name in factors], axis=2)


def _fit(cube, family, schedule, quantile, alpha):
    factors = FACTOR_SETS[family]
    decision, exit_bar = schedule
    entry = decision + 1
    matrix = _matrix(cube, factors, decision)
    asset_return = cube.opens[:, exit_bar, ASSETS] / cube.opens[:, entry, ASSETS] - 1.0 - v34.STANDARD_COST
    spy_return = cube.opens[:, exit_bar, 0] / cube.opens[:, entry, 0] - 1.0
    target = asset_return - spy_return[:, None]
    quality = (cube.first[:, entry, ASSETS] <= entry * 5) & (cube.first[:, exit_bar, ASSETS] <= exit_bar * 5)
    finite = np.isfinite(matrix).all(axis=2) & np.isfinite(target) & quality
    train = cube.masks()["train_2022_2023"][:, None] & finite
    values, labels = matrix[train], target[train]
    mean, scale = values.mean(axis=0), values.std(axis=0)
    scale[scale < 1e-8] = 1.0
    standardized = (values - mean) / scale
    coefficients = np.linalg.solve(standardized.T @ standardized + alpha * np.eye(len(factors)), standardized.T @ labels)
    score = np.einsum("saf,f->sa", (matrix - mean) / scale, coefficients)
    score = np.where(np.isfinite(matrix).all(axis=2), score, -np.inf)
    best = np.max(score, axis=1)
    train_days = cube.masks()["train_2022_2023"] & np.isfinite(best)
    threshold = float(np.quantile(best[train_days], quantile))
    return Model(family, factors, decision, exit_bar, quantile, alpha, mean, scale, coefficients, threshold)


def _raw(cube, model, cost, delay):
    matrix = _matrix(cube, model.factors, model.decision)
    score = np.einsum("saf,f->sa", (matrix - model.mean) / model.scale, model.coefficients)
    score = np.where(np.isfinite(matrix).all(axis=2), score, -np.inf)
    local = np.argmax(score, axis=1)
    selected = ASSETS[local]
    best = score[cube.rows, local]
    entry = model.decision + 1 + delay
    exit_bar = model.exit_bar
    active = np.isfinite(best) & (best >= model.threshold)
    active &= cube.first[cube.rows, entry, selected] <= entry * 5
    active &= cube.first[cube.rows, exit_bar, selected] <= exit_bar * 5
    active &= np.isfinite(cube.opens[cube.rows, entry, selected]) & np.isfinite(cube.opens[cube.rows, exit_bar, selected])
    active &= np.isfinite(cube.opens[:, entry, 0]) & np.isfinite(cube.opens[:, exit_bar, 0])
    values = np.zeros(len(cube.sessions))
    values[active] = cube.opens[active, exit_bar, selected[active]] / cube.opens[active, entry, selected[active]] - 1.0 - cost
    benchmark = np.zeros(len(cube.sessions))
    benchmark[active] = cube.opens[active, exit_bar, 0] / cube.opens[active, entry, 0] - 1.0
    return v34.v12.ReturnStream(values, benchmark, active, active.astype(int))


def _streams(cube, model):
    raw = (_raw(cube, model, v34.STANDARD_COST, 0), _raw(cube, model, v34.STRESS_COST, 0), _raw(cube, model, v34.STANDARD_COST, 1))
    exposure = v42._exposure(raw[0].values, 20, 0.40, 0.0)
    return tuple(v42._scaled(stream, exposure) for stream in raw)


def _primary(observation):
    oos = observation["development_oos_2024_2025"]
    return float(oos["annualized_return"]) >= 0.50 and float(oos["max_drawdown"]) < 0.20 and float(oos["information_ratio"]) >= 1.0 and all(float(observation[name]["annualized_return"]) > 0 for name in ("train_2022_2023", "2024", "2025"))


def _rank(observations):
    return (min(float(item["development_oos_2024_2025"]["annualized_return"]) for item in observations), min(float(item["development_oos_2024_2025"]["information_ratio"]) for item in observations), min(float(observations[0][name]["annualized_return"]) for name in ("train_2022_2023", "2024", "2025")))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = IntradayPathCube(args.root, "alpaca", 0)
    historical = IntradayPathCube(args.root, "historical", 0)
    cells = []
    for offset, (family, schedule, quantile, alpha) in enumerate(specifications()):
        model = _fit(development, family, schedule, quantile, alpha)
        streams = _streams(development, model)
        observations = tuple(v47._observe(development, stream, True) for stream in streams)
        cells.append({"version": FIRST_VERSION + offset, "family": family, "schedule": schedule, "quantile": quantile, "alpha": alpha, "model": model, "streams": streams, "observations": observations, "rank": _rank(observations), "primary": all(_primary(item) for item in observations)})
    total_cells = PRIOR_COMPARISON_CELLS + len(cells)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    for cell in cells:
        historical_streams = _streams(historical, cell["model"])
        historical_obs = tuple(v47._observe(historical, stream, True)["historical_2018_2020"] for stream in historical_streams)
        streams, observations = cell["streams"], cell["observations"]
        fold_metrics = {name: [metrics(stream.values[index], stream.benchmark[index], stream.active[index]) for index in folds] for name, stream in zip(("standard", "cost_18bp", "delay_5min_9bp"), streams, strict=True)}
        starts = {}
        for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
            mask = development.masks()["development_all"] & (development.dates >= pd.Timestamp(start))
            starts[start] = metrics(streams[0].values[mask], streams[0].benchmark[mask], streams[0].active[mask])
        q_index = QUANTILES.index(cell["quantile"])
        neighbors = [item for item in cells if item["family"] == cell["family"] and item["schedule"] == cell["schedule"] and item["alpha"] == cell["alpha"] and abs(QUANTILES.index(item["quantile"]) - q_index) <= 1]
        neighborhood = sum(item["primary"] for item in neighbors) / len(neighbors)
        oos = observations[0]["development_oos_2024_2025"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * v47._normal_tail(abs(z_score)) * total_cells)
        gates = {"standard_primary": _primary(observations[0]), "cost_18bp_primary": _primary(observations[1]), "delay_5min_primary": _primary(observations[2]), "four_of_five_positive_folds_all_scenarios": all(sum(float(item["annualized_return"]) > 0 for item in values) >= 4 for values in fold_metrics.values()), "all_start_dates_positive": all(float(item["annualized_return"]) > 0 for item in starts.values()), "historical_15pct_mdd_below_20pct_all_scenarios": all(float(item["annualized_return"]) >= 0.15 and float(item["max_drawdown"]) < 0.20 for item in historical_obs), "parameter_neighborhood_70pct_primary": neighborhood >= 0.70, "consumed_2026q1_above_5pct": float(observations[0]["consumed_2026q1"]["total_return"]) > 0.05, "consumed_2026_total_above_5pct": float(observations[0]["consumed_2026_all"]["total_return"]) > 0.05, "cumulative_bonferroni_5pct": bonferroni < 0.05}
        model = cell["model"]
        definition = {"version": cell["version"], "mechanism": "multifactor_residual_alpha", "factor_set": cell["family"], "decision": model.decision, "exit": model.exit_bar, "score_quantile": model.quantile, "ridge_alpha": model.alpha, "target_volatility": 0.40, "lookback": 20}
        records.append({"candidate_id": f"lev-v{cell['version']}-" + _identity(definition), "definition": definition, "model": {"factors": model.factors, "mean": model.mean.tolist(), "scale": model.scale.tolist(), "coefficients": model.coefficients.tolist(), "threshold": model.threshold}, "standard": observations[0], "cost_18bp": observations[1], "delay_5min_9bp": observations[2], "historical_scenarios": {"standard": historical_obs[0], "cost_18bp": historical_obs[1], "delay_5min_9bp": historical_obs[2]}, "development_folds": fold_metrics, "start_date_stress": starts, "neighbor_primary_share": neighborhood, "multiple_comparison": {"total_cells": total_cells, "z_score": z_score, "bonferroni_p": bonferroni}, "gates": gates, "strict_pre_factory_null_pass": all(gates.values())})
    records.sort(key=lambda item: _rank((item["standard"], item["cost_18bp"], item["delay_5min_9bp"])), reverse=True)
    payload = {"schema_version": "1.0.0", "status": "COMPLETE", "version_range": [FIRST_VERSION, LAST_VERSION], "evaluated_cells": len(cells), "comparison_cells": total_cells, "strict_pre_factory_null_passes": sum(item["strict_pre_factory_null_pass"] for item in records), "elapsed_seconds": time.perf_counter() - started, "records": records}
    v34.v12._atomic(args.output, payload)
    print(json.dumps({"status": "COMPLETE", "evaluated_cells": len(cells), "strict_pre_factory_null_passes": payload["strict_pre_factory_null_passes"], "best": records[0]["candidate_id"], "elapsed_seconds": payload["elapsed_seconds"]}))


if __name__ == "__main__":
    main()
