"""Preregistered bar-2 multifactor gate over the frozen v4423 transfer sleeve."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import time
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v39_multifactor_regime_gate as v39
import evaluate_full_universe_intraday_v47_score_slope as v47
import evaluate_full_universe_intraday_v248_v347_mechanism_campaign as state
import evaluate_full_universe_intraday_v4070_v4169_state_routed_v42 as prior
import evaluate_full_universe_intraday_v4170_v4269_dual_parent_routing as dual
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 4470
LAST_VERSION = 4569
PRIOR_COMPARISON_CELLS = 253_105
SOURCE_SHA256 = prior.SOURCE_SHA256
MODERN_PARENT = dual.MODERN_PARENT
TRANSFER_PARENT = "lev-v42t-b5dc591391ab516c"
GATE_DECISION = 2
TRANSFER_ENTRY = 3
ASSETS = np.asarray((3, 4), dtype=int)
QUANTILES = (0.0, 0.2, 0.4, 0.6, 0.8)
ALPHAS = (1.0, 100.0)
FACTOR_SETS = {
    "trend_flow": ("current_return", "relative_return", "trend_consistency", "signed_volume_imbalance"),
    "trend_structure": ("current_return", "relative_return", "vwap_distance", "close_location"),
    "flow_structure": ("signed_volume_imbalance", "volume_acceleration", "vwap_distance", "close_location"),
    "breakout_quality": ("current_return", "path_efficiency", "close_location", "session_range"),
    "reclaim_quality": ("recent_return", "vwap_distance", "close_location", "signed_volume_imbalance"),
    "cross_persistence": ("current_return", "relative_return", "current_rank", "prior20_rank", "prior20_return"),
    "gap_followthrough": ("gap", "current_return", "path_efficiency", "signed_volume_imbalance"),
    "volatility_flow": ("realized_volatility", "session_range", "signed_volume_imbalance", "volume_acceleration"),
    "state_conditioned_trend": ("current_return", "relative_return", "prior1_return", "prior20_return", "spy_prior20", "spy_volatility"),
    "balanced_early": ("current_return", "relative_return", "path_efficiency", "signed_volume_imbalance", "vwap_distance", "close_location", "prior20_return", "spy_volatility"),
}


def specifications():
    return list(itertools.product(FACTOR_SETS, QUANTILES, ALPHAS))


def _identity(definition: dict) -> str:
    encoded = json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _daily_matrix(cube, factors):
    available = cube.factors(GATE_DECISION)
    columns = []
    for name in factors:
        values = available[name][:, ASSETS]
        finite = np.isfinite(values)
        count = finite.sum(axis=1)
        columns.append(np.divide(np.nansum(values, axis=1), count, out=np.full(len(values), np.nan), where=count > 0))
    return np.stack(columns, axis=1)


def _fit_gate(cube, transfer_standard, base_transfer, factors, quantile, alpha):
    matrix = _daily_matrix(cube, factors)
    train = cube.masks()["train_2022_2023"] & base_transfer & transfer_standard.active & np.isfinite(matrix).all(axis=1)
    values = matrix[train]
    target = (transfer_standard.values - transfer_standard.benchmark)[train]
    mean, scale = values.mean(axis=0), values.std(axis=0)
    scale[scale < 1e-8] = 1.0
    standardized = (values - mean) / scale
    coefficients = np.linalg.solve(standardized.T @ standardized + alpha * np.eye(len(factors)), standardized.T @ target)
    score = np.einsum("sf,f->s", (matrix - mean) / scale, coefficients)
    threshold = float(np.quantile(score[train & np.isfinite(score)], quantile))
    return {"factors": factors, "mean": mean, "scale": scale, "coefficients": coefficients, "threshold": threshold}


def _score(cube, model):
    matrix = _daily_matrix(cube, model["factors"])
    return np.einsum("sf,f->s", (matrix - model["mean"]) / model["scale"], model["coefficients"])


def _base_state(cube_state, core_model, override_model):
    core_score = dual._score(cube_state, core_model)
    core_modern = np.isfinite(core_score) & (core_score >= core_model["threshold"])
    override_score = dual._score(cube_state, override_model)
    override_low = np.isfinite(override_score) & (override_score < override_model["threshold"])
    base_modern = core_modern | ((~core_modern) & override_low)
    return base_modern, ~base_modern


def _route(parent_streams, base_modern, allow_transfer):
    active_transfer = (~base_modern) & allow_transfer
    output = []
    for modern, transfer in zip(parent_streams[MODERN_PARENT], parent_streams[TRANSFER_PARENT], strict=True):
        values = np.where(base_modern, modern.values, np.where(active_transfer, transfer.values, 0.0))
        benchmark = np.where(base_modern, modern.benchmark, np.where(active_transfer, transfer.benchmark, 0.0))
        active = np.where(base_modern, modern.active, active_transfer & transfer.active)
        trades = np.where(base_modern, modern.component_trades, np.where(active_transfer, transfer.component_trades, 0))
        output.append(v34.v12.ReturnStream(values, benchmark, active, trades))
    return tuple(output)


def _primary(observation):
    oos = observation["development_oos_2024_2025"]
    return float(oos["annualized_return"]) >= 0.50 and float(oos["max_drawdown"]) < 0.20 and float(oos["information_ratio"]) >= 1.0 and all(float(observation[name]["annualized_return"]) > 0 for name in ("train_2022_2023", "2024", "2025"))


def _rank(observations):
    return (min(float(item["development_oos_2024_2025"]["annualized_return"]) for item in observations), min(float(item["development_oos_2024_2025"]["information_ratio"]) for item in observations), min(float(observations[0][name]["annualized_return"]) for name in ("train_2022_2023", "2024", "2025")))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if prior._sha(args.source) != SOURCE_SHA256:
        raise RuntimeError("V42_SOURCE_HASH_CHANGED")
    started = time.perf_counter()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    parent_map = {item["candidate_id"]: item for item in source["records"]}
    required = (MODERN_PARENT, TRANSFER_PARENT)
    if any(item not in parent_map for item in required) or len(specifications()) != 100:
        raise RuntimeError("EARLY_GATE_PREREGISTRATION_MISMATCH")
    development = v34.Cube(args.root, "alpaca", 0)
    historical = v34.Cube(args.root, "historical", 0)
    development_state = state.v53.Cube(args.root, "alpaca", 0)
    historical_state = state.v53.Cube(args.root, "historical", 0)
    if not np.array_equal(development.dates, development_state.dates) or not np.array_equal(historical.dates, historical_state.dates):
        raise RuntimeError("STATE_AND_PARENT_CUBES_MISALIGNED")
    models = {item: v39._models(development, [parent_map[item]["definition"]["strategy"]])[0] for item in required}
    dev_parents = {item: prior._parent_streams(development, parent_map[item], models[item]) for item in required}
    hist_parents = {item: prior._parent_streams(historical, parent_map[item], models[item]) for item in required}
    core_model = dual._fit_state(development_state, dual.STATE_FAMILIES["low_dispersion_trend"], 0.20)
    override_model = dual._fit_state(development_state, dual.STATE_FAMILIES["oversold_repair"], 0.35)
    dev_modern, dev_transfer = _base_state(development_state, core_model, override_model)
    hist_modern, _ = _base_state(historical_state, core_model, override_model)
    cells = []
    for offset, (family, quantile, alpha) in enumerate(specifications()):
        gate_model = _fit_gate(development, dev_parents[TRANSFER_PARENT][0], dev_transfer, FACTOR_SETS[family], quantile, alpha)
        score = _score(development, gate_model)
        allow = np.isfinite(score) & (score >= gate_model["threshold"])
        streams = _route(dev_parents, dev_modern, allow)
        observations = tuple(v47._observe(development, stream, True) for stream in streams)
        cells.append({"version": FIRST_VERSION + offset, "family": family, "quantile": quantile, "alpha": alpha, "model": gate_model, "streams": streams, "observations": observations, "rank": _rank(observations), "primary": all(_primary(item) for item in observations)})
    total_cells = PRIOR_COMPARISON_CELLS + len(cells)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    for cell in cells:
        hist_score = _score(historical, cell["model"])
        hist_allow = np.isfinite(hist_score) & (hist_score >= cell["model"]["threshold"])
        historical_streams = _route(hist_parents, hist_modern, hist_allow)
        historical_obs = tuple(v47._observe(historical, stream, True)["historical_2018_2020"] for stream in historical_streams)
        streams, observations = cell["streams"], cell["observations"]
        fold_metrics = {name: [metrics(stream.values[index], stream.benchmark[index], stream.active[index]) for index in folds] for name, stream in zip(("standard", "cost_18bp", "delay_5min_9bp"), streams, strict=True)}
        starts = {}
        for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
            mask = development.masks()["development_all"] & (development.dates >= pd.Timestamp(start))
            starts[start] = metrics(streams[0].values[mask], streams[0].benchmark[mask], streams[0].active[mask])
        q_index, a_index = QUANTILES.index(cell["quantile"]), ALPHAS.index(cell["alpha"])
        neighbors = [item for item in cells if item["family"] == cell["family"] and abs(QUANTILES.index(item["quantile"]) - q_index) + abs(ALPHAS.index(item["alpha"]) - a_index) <= 1]
        neighborhood = sum(item["primary"] for item in neighbors) / len(neighbors)
        oos = observations[0]["development_oos_2024_2025"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * v47._normal_tail(abs(z_score)) * total_cells)
        gates = {
            "standard_primary": _primary(observations[0]), "cost_18bp_primary": _primary(observations[1]), "delay_5min_primary": _primary(observations[2]),
            "four_of_five_positive_folds_all_scenarios": all(sum(float(item["annualized_return"]) > 0 for item in values) >= 4 for values in fold_metrics.values()),
            "all_start_dates_positive": all(float(item["annualized_return"]) > 0 for item in starts.values()),
            "historical_15pct_mdd_below_20pct_all_scenarios": all(float(item["annualized_return"]) >= 0.15 and float(item["max_drawdown"]) < 0.20 for item in historical_obs),
            "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
            "consumed_2026q1_above_5pct": float(observations[0]["consumed_2026q1"]["total_return"]) > 0.05,
            "consumed_2026_total_above_5pct": float(observations[0]["consumed_2026_all"]["total_return"]) > 0.05,
            "cumulative_bonferroni_5pct": bonferroni < 0.05,
        }
        definition = {"version": cell["version"], "mechanism": "v4423_bar2_multifactor_transfer_gate", "base_candidate": "lev-v4423-5298677326af2b2b", "factor_set": cell["family"], "score_quantile": cell["quantile"], "ridge_alpha": cell["alpha"]}
        model = cell["model"]
        records.append({"candidate_id": f"lev-v{cell['version']}-" + _identity(definition), "definition": definition, "gate_model": {"factors": model["factors"], "mean": model["mean"].tolist(), "scale": model["scale"].tolist(), "coefficients": model["coefficients"].tolist(), "threshold": model["threshold"]}, "standard": observations[0], "cost_18bp": observations[1], "delay_5min_9bp": observations[2], "historical_scenarios": {"standard": historical_obs[0], "cost_18bp": historical_obs[1], "delay_5min_9bp": historical_obs[2]}, "development_folds": fold_metrics, "start_date_stress": starts, "neighbor_primary_share": neighborhood, "multiple_comparison": {"total_cells": total_cells, "z_score": z_score, "bonferroni_p": bonferroni}, "gates": gates, "strict_pre_factory_null_pass": all(gates.values())})
    records.sort(key=lambda item: _rank((item["standard"], item["cost_18bp"], item["delay_5min_9bp"])), reverse=True)
    payload = {"schema_version": "1.0.0", "status": "COMPLETE", "version_range": [FIRST_VERSION, LAST_VERSION], "evaluated_cells": len(cells), "comparison_cells": total_cells, "strict_pre_factory_null_passes": sum(item["strict_pre_factory_null_pass"] for item in records), "elapsed_seconds": time.perf_counter() - started, "records": records}
    v34.v12._atomic(args.output, payload)
    print(json.dumps({"status": "COMPLETE", "evaluated_cells": len(cells), "strict_pre_factory_null_passes": payload["strict_pre_factory_null_passes"], "best": records[0]["candidate_id"], "elapsed_seconds": payload["elapsed_seconds"]}))


if __name__ == "__main__":
    main()
