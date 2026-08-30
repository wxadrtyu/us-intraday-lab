"""Preregistered shallow nonlinear bar-17 meta-gate over the frozen route."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import time
from pathlib import Path

import evaluate_full_universe_intraday_v30_extra_trees as trees
import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v39_multifactor_regime_gate as v39
import evaluate_full_universe_intraday_v47_score_slope as v47
import evaluate_full_universe_intraday_v4070_v4169_state_routed_v42 as prior
import evaluate_full_universe_intraday_v4170_v4269_dual_parent_routing as dual
import evaluate_full_universe_intraday_v4470_v4569_early_quality_gate as transfer_gate
import evaluate_full_universe_intraday_v5670_v5769_modern_quality_gate as linear_gate
import numpy as np
import pandas as pd
from evaluate_full_universe_intraday_v1463_v1562_intraday_path_multifactor import IntradayPathCube

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 5870
LAST_VERSION = 5969
PRIOR_COMPARISON_CELLS = 254_505
SOURCE_SHA256 = prior.SOURCE_SHA256
MODERN_PARENT = transfer_gate.MODERN_PARENT
TRANSFER_PARENT = transfer_gate.TRANSFER_PARENT
GATE_DECISION = 17
MODERN_ENTRY = 24
ASSETS = np.asarray((3, 4), dtype=int)
QUANTILES = (0.0, 0.2, 0.4, 0.6, 0.8)
TREE_CONFIGS = ((2, 15), (2, 25), (3, 15), (4, 15))
FACTOR_SETS = {
    "path_flow": ("current_return", "relative_return", "path_efficiency", "signed_volume_imbalance", "volume_acceleration", "drawdown_from_high", "rebound_from_low", "return_acceleration"),
    "structure_state": ("vwap_distance", "close_location", "range_ratio", "session_range", "prior1_return", "prior20_return", "spy_prior20", "spy_volatility"),
    "cross_path": ("relative_return", "current_rank", "prior20_rank", "sector_breadth", "path_efficiency", "intraday_range_position", "return_acceleration"),
    "contraction_repair": ("recent_volatility_ratio", "recent_volume_ratio", "drawdown_from_high", "rebound_from_low", "return_acceleration", "close_location"),
    "balanced": ("current_return", "relative_return", "path_efficiency", "signed_volume_imbalance", "vwap_distance", "close_location", "drawdown_from_high", "rebound_from_low", "return_acceleration", "prior20_return", "spy_volatility"),
}
MECHANISM = "v4513_nonlinear_bar17_meta_gate"


def specifications():
    return list(itertools.product(FACTOR_SETS, TREE_CONFIGS, QUANTILES))


def _identity(definition):
    encoded = json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _matrix(cube, factors):
    available = cube.factors(GATE_DECISION)
    columns = []
    for name in factors:
        values = available[name][:, ASSETS]
        finite = np.isfinite(values)
        count = finite.sum(axis=1)
        columns.append(np.divide(np.nansum(values, axis=1), count, out=np.full(len(values), np.nan), where=count > 0))
    return np.stack(columns, axis=1)


def _fit(cube, modern, base_modern, factors, depth, min_leaf, quantile, seed):
    matrix = _matrix(cube, factors)
    train = cube.masks()["train_2022_2023"] & base_modern & modern.active
    medians = np.nanmedian(matrix[train], axis=0)
    values = np.where(np.isfinite(matrix), matrix, medians)
    target = modern.values - modern.benchmark
    selected = values[train]
    labels = target[train]
    generator = np.random.default_rng(seed)
    forest = []
    for _ in range(64):
        sample = generator.integers(0, len(labels), size=len(labels))
        forest.append(trees._fit_node(selected[sample], labels[sample], depth, min_leaf, generator))
    prediction = trees._predict(forest, values)
    threshold = float(np.quantile(prediction[train], quantile))
    return {"factors": factors, "medians": medians, "trees": forest, "threshold": threshold}


def _predict(cube, model):
    matrix = _matrix(cube, model["factors"])
    values = np.where(np.isfinite(matrix), matrix, model["medians"])
    return trees._predict(model["trees"], values)


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
    dev_parents = {item: prior._parent_streams(development, parent_map[item], models[item]) for item in required}
    hist_parents = {item: prior._parent_streams(historical, parent_map[item], models[item]) for item in required}
    core_model = dual._fit_state(development, dual.STATE_FAMILIES["low_dispersion_trend"], 0.20)
    override_model = dual._fit_state(development, dual.STATE_FAMILIES["oversold_repair"], 0.35)
    dev_modern, dev_transfer = transfer_gate._base_state(development, core_model, override_model)
    hist_modern, _ = transfer_gate._base_state(historical, core_model, override_model)
    transfer_model = transfer_gate._fit_gate(development, dev_parents[TRANSFER_PARENT][0], dev_transfer, transfer_gate.FACTOR_SETS["reclaim_quality"], 0.20, 100.0)
    dev_transfer_score = transfer_gate._score(development, transfer_model)
    hist_transfer_score = transfer_gate._score(historical, transfer_model)
    dev_allow_transfer = np.isfinite(dev_transfer_score) & (dev_transfer_score >= transfer_model["threshold"])
    hist_allow_transfer = np.isfinite(hist_transfer_score) & (hist_transfer_score >= transfer_model["threshold"])
    cells = []
    for offset, (family, config, quantile) in enumerate(specifications()):
        depth, min_leaf = config
        model = _fit(development, dev_parents[MODERN_PARENT][0], dev_modern, FACTOR_SETS[family], depth, min_leaf, quantile, 20260830 + offset * 100)
        prediction = _predict(development, model)
        allow_modern = np.isfinite(prediction) & (prediction >= model["threshold"])
        streams = linear_gate._route(dev_parents, dev_modern, allow_modern, dev_allow_transfer)
        observations = tuple(v47._observe(development, stream, True) for stream in streams)
        cells.append({"version": FIRST_VERSION + offset, "family": family, "depth": depth, "min_leaf": min_leaf, "quantile": quantile, "model": model, "streams": streams, "observations": observations, "rank": _rank(observations), "primary": all(_primary(item) for item in observations)})
    total_cells = PRIOR_COMPARISON_CELLS + len(cells)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    for cell in cells:
        prediction = _predict(historical, cell["model"])
        allow_modern = np.isfinite(prediction) & (prediction >= cell["model"]["threshold"])
        historical_streams = linear_gate._route(hist_parents, hist_modern, allow_modern, hist_allow_transfer)
        historical_obs = tuple(v47._observe(historical, stream, True)["historical_2018_2020"] for stream in historical_streams)
        streams, observations = cell["streams"], cell["observations"]
        fold_metrics = {name: [metrics(stream.values[index], stream.benchmark[index], stream.active[index]) for index in folds] for name, stream in zip(("standard", "cost_18bp", "delay_5min_9bp"), streams, strict=True)}
        starts = {}
        for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
            mask = development.masks()["development_all"] & (development.dates >= pd.Timestamp(start))
            starts[start] = metrics(streams[0].values[mask], streams[0].benchmark[mask], streams[0].active[mask])
        q_index = QUANTILES.index(cell["quantile"])
        neighbors = [item for item in cells if item["family"] == cell["family"] and item["depth"] == cell["depth"] and item["min_leaf"] == cell["min_leaf"] and abs(QUANTILES.index(item["quantile"]) - q_index) <= 1]
        neighborhood = sum(item["primary"] for item in neighbors) / len(neighbors)
        oos = observations[0]["development_oos_2024_2025"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * v47._normal_tail(abs(z_score)) * total_cells)
        gates = {"standard_primary": _primary(observations[0]), "cost_18bp_primary": _primary(observations[1]), "delay_5min_primary": _primary(observations[2]), "four_of_five_positive_folds_all_scenarios": all(sum(float(item["annualized_return"]) > 0 for item in values) >= 4 for values in fold_metrics.values()), "all_start_dates_positive": all(float(item["annualized_return"]) > 0 for item in starts.values()), "historical_15pct_mdd_below_20pct_all_scenarios": all(float(item["annualized_return"]) >= 0.15 and float(item["max_drawdown"]) < 0.20 for item in historical_obs), "parameter_neighborhood_70pct_primary": neighborhood >= 0.70, "consumed_2026q1_above_5pct": float(observations[0]["consumed_2026q1"]["total_return"]) > 0.05, "consumed_2026_total_above_5pct": float(observations[0]["consumed_2026_all"]["total_return"]) > 0.05, "cumulative_bonferroni_5pct": bonferroni < 0.05}
        definition = {"version": cell["version"], "mechanism": MECHANISM, "factor_set": cell["family"], "tree_depth": cell["depth"], "minimum_leaf": cell["min_leaf"], "score_quantile": cell["quantile"], "trees": 64}
        records.append({"candidate_id": f"lev-v{cell['version']}-" + _identity(definition), "definition": definition, "standard": observations[0], "cost_18bp": observations[1], "delay_5min_9bp": observations[2], "historical_scenarios": {"standard": historical_obs[0], "cost_18bp": historical_obs[1], "delay_5min_9bp": historical_obs[2]}, "development_folds": fold_metrics, "start_date_stress": starts, "neighbor_primary_share": neighborhood, "multiple_comparison": {"total_cells": total_cells, "z_score": z_score, "bonferroni_p": bonferroni}, "gates": gates, "strict_pre_factory_null_pass": all(gates.values())})
    records.sort(key=lambda item: _rank((item["standard"], item["cost_18bp"], item["delay_5min_9bp"])), reverse=True)
    payload = {"schema_version": "1.0.0", "status": "COMPLETE", "version_range": [FIRST_VERSION, LAST_VERSION], "evaluated_cells": len(cells), "comparison_cells": total_cells, "strict_pre_factory_null_passes": sum(item["strict_pre_factory_null_pass"] for item in records), "elapsed_seconds": time.perf_counter() - started, "records": records}
    v34.v12._atomic(args.output, payload)
    print(json.dumps({"status": "COMPLETE", "evaluated_cells": len(cells), "strict_pre_factory_null_passes": payload["strict_pre_factory_null_passes"], "best": records[0]["candidate_id"], "elapsed_seconds": payload["elapsed_seconds"]}))


if __name__ == "__main__":
    main()
