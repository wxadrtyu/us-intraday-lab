"""Preregistered bounded dual-asset allocation inside the frozen weak-market route."""

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
import evaluate_full_universe_intraday_v42_multifactor_vol_target as v42
import evaluate_full_universe_intraday_v47_score_slope as v47
import evaluate_full_universe_intraday_v4070_v4169_state_routed_v42 as prior
import evaluate_full_universe_intraday_v4170_v4269_dual_parent_routing as dual
import evaluate_full_universe_intraday_v4470_v4569_early_quality_gate as transfer_gate
import numpy as np
import pandas as pd
from evaluate_full_universe_intraday_v1463_v1562_intraday_path_multifactor import IntradayPathCube

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 5770
LAST_VERSION = 5869
PRIOR_COMPARISON_CELLS = 254_405
SOURCE_SHA256 = prior.SOURCE_SHA256
MODERN_PARENT = transfer_gate.MODERN_PARENT
TRANSFER_PARENT = transfer_gate.TRANSFER_PARENT
MAX_WEIGHTS = (0.50, 0.60, 0.70, 0.80, 1.00)
SCORE_BUFFERS = (-0.10, -0.05, 0.0, 0.05, 0.10)
TEMPERATURES = (0.10, 0.50)
TARGETS = (0.35, 0.40)


def specifications():
    return list(itertools.product(MAX_WEIGHTS, SCORE_BUFFERS, TEMPERATURES, TARGETS))


def _identity(definition):
    encoded = json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _weights(score, maximum, temperature):
    shifted = (score - np.max(score, axis=1, keepdims=True)) / temperature
    raw = np.exp(np.clip(shifted, -50.0, 0.0))
    raw /= raw.sum(axis=1, keepdims=True)
    if maximum < 1.0:
        winner = np.argmax(raw, axis=1)
        capped = np.full_like(raw, 1.0 - maximum)
        capped[np.arange(len(raw)), winner] = maximum
        raw = np.where((raw.max(axis=1) > maximum)[:, None], capped, raw)
    return raw


def _raw(cube, model, cost, delay, maximum, buffer, temperature):
    matrix, _, _ = v34._matrix(cube, model.specification, model.factors)
    score = np.einsum("saf,f,f->sa", (matrix - model.mean) / model.scale, model.direction, model.weights)
    finite_score = np.isfinite(matrix).all(axis=2)
    score = np.where(finite_score, score, -np.inf)
    entry = int(model.specification["decision"]) + 1 + delay
    exit_bar = int(model.specification["exit"])
    assets = np.asarray(model.specification["assets"], dtype=int)
    quality = (cube.first[:, entry, assets] <= entry * 5) & (cube.first[:, exit_bar, assets] <= exit_bar * 5)
    quality &= np.isfinite(cube.opens[:, entry, assets]) & np.isfinite(cube.opens[:, exit_bar, assets])
    quality &= cube.opens[:, entry, assets] > 0
    valid = finite_score & quality
    safe_score = np.where(valid, score, -1e6)
    weights = _weights(safe_score, maximum, temperature)
    weights = np.where(valid, weights, 0.0)
    weight_sum = weights.sum(axis=1)
    weights = np.divide(weights, weight_sum[:, None], out=np.zeros_like(weights), where=weight_sum[:, None] > 0)
    best = np.max(score, axis=1)
    active = np.isfinite(best) & (best >= model.threshold + buffer) & (weight_sum > 0)
    active &= np.isfinite(cube.opens[:, entry, 0]) & np.isfinite(cube.opens[:, exit_bar, 0])
    asset_returns = cube.opens[:, exit_bar, assets] / cube.opens[:, entry, assets] - 1.0
    values = np.zeros(len(cube.sessions))
    values[active] = np.sum(weights[active] * asset_returns[active], axis=1) - cost
    benchmark = np.zeros(len(cube.sessions))
    benchmark[active] = cube.opens[active, exit_bar, 0] / cube.opens[active, entry, 0] - 1.0
    trades = np.where(active, (weights > 0).sum(axis=1), 0)
    return v34.v12.ReturnStream(values, benchmark, active, trades)


def _parent_streams(cube, parent, model, maximum, buffer, temperature, target):
    raw = (_raw(cube, model, v34.STANDARD_COST, 0, maximum, buffer, temperature), _raw(cube, model, v34.STRESS_COST, 0, maximum, buffer, temperature), _raw(cube, model, v34.STANDARD_COST, 1, maximum, buffer, temperature))
    exposure = v42._exposure(raw[0].values, int(parent["definition"]["lookback"]), target, float(parent["definition"]["minimum_exposure"]))
    return tuple(v42._scaled(stream, exposure) for stream in raw)


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
    development = IntradayPathCube(args.root, "alpaca", 0)
    historical = IntradayPathCube(args.root, "historical", 0)
    required = (MODERN_PARENT, TRANSFER_PARENT)
    models = {item: v39._models(development, [parent_map[item]["definition"]["strategy"]])[0] for item in required}
    core_model = dual._fit_state(development, dual.STATE_FAMILIES["low_dispersion_trend"], 0.20)
    override_model = dual._fit_state(development, dual.STATE_FAMILIES["oversold_repair"], 0.35)
    dev_modern, dev_transfer = transfer_gate._base_state(development, core_model, override_model)
    hist_modern, _ = transfer_gate._base_state(historical, core_model, override_model)
    cells = []
    for offset, (maximum, buffer, temperature, target) in enumerate(specifications()):
        dev_parents = {item: _parent_streams(development, parent_map[item], models[item], maximum, buffer, temperature, target) for item in required}
        quality_model = transfer_gate._fit_gate(development, dev_parents[TRANSFER_PARENT][0], dev_transfer, transfer_gate.FACTOR_SETS["reclaim_quality"], 0.20, 100.0)
        quality_score = transfer_gate._score(development, quality_model)
        allow_transfer = np.isfinite(quality_score) & (quality_score >= quality_model["threshold"])
        streams = transfer_gate._route(dev_parents, dev_modern, allow_transfer)
        observations = tuple(v47._observe(development, stream, True) for stream in streams)
        cells.append({"version": FIRST_VERSION + offset, "maximum": maximum, "buffer": buffer, "temperature": temperature, "target": target, "quality_model": quality_model, "streams": streams, "observations": observations, "rank": _rank(observations), "primary": all(_primary(item) for item in observations)})
    total_cells = PRIOR_COMPARISON_CELLS + len(cells)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    for cell in cells:
        hist_parents = {item: _parent_streams(historical, parent_map[item], models[item], cell["maximum"], cell["buffer"], cell["temperature"], cell["target"]) for item in required}
        quality_score = transfer_gate._score(historical, cell["quality_model"])
        allow_transfer = np.isfinite(quality_score) & (quality_score >= cell["quality_model"]["threshold"])
        historical_streams = transfer_gate._route(hist_parents, hist_modern, allow_transfer)
        historical_obs = tuple(v47._observe(historical, stream, True)["historical_2018_2020"] for stream in historical_streams)
        streams, observations = cell["streams"], cell["observations"]
        fold_metrics = {name: [metrics(stream.values[index], stream.benchmark[index], stream.active[index]) for index in folds] for name, stream in zip(("standard", "cost_18bp", "delay_5min_9bp"), streams, strict=True)}
        starts = {}
        for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
            mask = development.masks()["development_all"] & (development.dates >= pd.Timestamp(start))
            starts[start] = metrics(streams[0].values[mask], streams[0].benchmark[mask], streams[0].active[mask])
        indices = (MAX_WEIGHTS.index(cell["maximum"]), SCORE_BUFFERS.index(cell["buffer"]), TEMPERATURES.index(cell["temperature"]), TARGETS.index(cell["target"]))
        neighbors = [item for item in cells if sum(abs(left - right) for left, right in zip(indices, (MAX_WEIGHTS.index(item["maximum"]), SCORE_BUFFERS.index(item["buffer"]), TEMPERATURES.index(item["temperature"]), TARGETS.index(item["target"])), strict=True)) <= 1]
        neighborhood = sum(item["primary"] for item in neighbors) / len(neighbors)
        oos = observations[0]["development_oos_2024_2025"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * v47._normal_tail(abs(z_score)) * total_cells)
        gates = {"standard_primary": _primary(observations[0]), "cost_18bp_primary": _primary(observations[1]), "delay_5min_primary": _primary(observations[2]), "four_of_five_positive_folds_all_scenarios": all(sum(float(item["annualized_return"]) > 0 for item in values) >= 4 for values in fold_metrics.values()), "all_start_dates_positive": all(float(item["annualized_return"]) > 0 for item in starts.values()), "historical_15pct_mdd_below_20pct_all_scenarios": all(float(item["annualized_return"]) >= 0.15 and float(item["max_drawdown"]) < 0.20 for item in historical_obs), "parameter_neighborhood_70pct_primary": neighborhood >= 0.70, "consumed_2026q1_above_5pct": float(observations[0]["consumed_2026q1"]["total_return"]) > 0.05, "consumed_2026_total_above_5pct": float(observations[0]["consumed_2026_all"]["total_return"]) > 0.05, "cumulative_bonferroni_5pct": bonferroni < 0.05}
        definition = {"version": cell["version"], "mechanism": "bounded_dual_asset_allocation", "maximum_asset_weight": cell["maximum"], "score_buffer": cell["buffer"], "softmax_temperature": cell["temperature"], "target_volatility": cell["target"]}
        records.append({"candidate_id": f"lev-v{cell['version']}-" + _identity(definition), "definition": definition, "standard": observations[0], "cost_18bp": observations[1], "delay_5min_9bp": observations[2], "historical_scenarios": {"standard": historical_obs[0], "cost_18bp": historical_obs[1], "delay_5min_9bp": historical_obs[2]}, "development_folds": fold_metrics, "start_date_stress": starts, "neighbor_primary_share": neighborhood, "multiple_comparison": {"total_cells": total_cells, "z_score": z_score, "bonferroni_p": bonferroni}, "gates": gates, "strict_pre_factory_null_pass": all(gates.values())})
    records.sort(key=lambda item: _rank((item["standard"], item["cost_18bp"], item["delay_5min_9bp"])), reverse=True)
    payload = {"schema_version": "1.0.0", "status": "COMPLETE", "version_range": [FIRST_VERSION, LAST_VERSION], "evaluated_cells": len(cells), "comparison_cells": total_cells, "strict_pre_factory_null_passes": sum(item["strict_pre_factory_null_pass"] for item in records), "elapsed_seconds": time.perf_counter() - started, "records": records}
    v34.v12._atomic(args.output, payload)
    print(json.dumps({"status": "COMPLETE", "evaluated_cells": len(cells), "strict_pre_factory_null_passes": payload["strict_pre_factory_null_passes"], "best": records[0]["candidate_id"], "elapsed_seconds": payload["elapsed_seconds"]}))


if __name__ == "__main__":
    main()
