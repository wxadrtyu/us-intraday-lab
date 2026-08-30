"""Preregistered temporal diversification of the frozen v4513 route."""

from __future__ import annotations

import argparse
import hashlib
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
import evaluate_full_universe_intraday_v4470_v4569_early_quality_gate as gate
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 4570
LAST_VERSION = 4669
PRIOR_COMPARISON_CELLS = 253_205
SOURCE_SHA256 = prior.SOURCE_SHA256
PARENT_COUNT = 20
WEIGHTS = (0.20, 0.225, 0.25, 0.275, 0.30)
MODERN_PARENT = gate.MODERN_PARENT
TRANSFER_PARENT = gate.TRANSFER_PARENT


def _identity(definition):
    encoded = json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _combine(base, sleeve, weight):
    return v34.v12.ReturnStream(
        (1 - weight) * base.values + weight * sleeve.values,
        (1 - weight) * base.benchmark + weight * sleeve.benchmark,
        base.active | sleeve.active,
        base.component_trades + sleeve.component_trades,
    )


def _base_streams(cube, cube_state, parents, core_model, override_model, quality_model):
    core_score = dual._score(cube_state, core_model)
    core_modern = np.isfinite(core_score) & (core_score >= core_model["threshold"])
    override_score = dual._score(cube_state, override_model)
    override_low = np.isfinite(override_score) & (override_score < override_model["threshold"])
    base_modern = core_modern | ((~core_modern) & override_low)
    quality_score = gate._score(cube, quality_model)
    allow_transfer = np.isfinite(quality_score) & (quality_score >= quality_model["threshold"])
    return gate._route(parents, base_modern, allow_transfer)


def _train_rank(cube, base, streams):
    train = cube.masks()["train_2022_2023"]
    observations = [metrics(stream.values[train], stream.benchmark[train], stream.active[train]) for stream in streams]
    correlation = np.corrcoef(base.values[train], streams[0].values[train])[0, 1]
    correlation = abs(float(correlation)) if np.isfinite(correlation) else 1.0
    return (min(float(item["annualized_return"]) for item in observations) - 0.25 * correlation, min(float(item["information_ratio"]) for item in observations), -correlation)


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
    temporal_ids = [item["candidate_id"] for item in source["records"] if int(item["definition"]["strategy"]["decision"]) == 5 and int(item["definition"]["strategy"]["exit"]) == 47]
    if len(temporal_ids) < PARENT_COUNT:
        raise RuntimeError("TEMPORAL_PARENT_UNIVERSE_TOO_SMALL")
    development = state.v53.Cube(args.root, "alpaca", 0)
    historical = state.v53.Cube(args.root, "historical", 0)
    required = (MODERN_PARENT, TRANSFER_PARENT, *temporal_ids)
    models = {item: v39._models(development, [parent_map[item]["definition"]["strategy"]])[0] for item in required}
    dev_parents = {item: prior._parent_streams(development, parent_map[item], models[item]) for item in required}
    hist_parents = {item: prior._parent_streams(historical, parent_map[item], models[item]) for item in required}
    core_model = dual._fit_state(development, dual.STATE_FAMILIES["low_dispersion_trend"], 0.20)
    override_model = dual._fit_state(development, dual.STATE_FAMILIES["oversold_repair"], 0.35)
    _, dev_transfer = gate._base_state(development, core_model, override_model)
    quality_model = gate._fit_gate(development, dev_parents[TRANSFER_PARENT][0], dev_transfer, gate.FACTOR_SETS["reclaim_quality"], 0.20, 100.0)
    base_dev = _base_streams(development, development, dev_parents, core_model, override_model, quality_model)
    base_hist = _base_streams(historical, historical, hist_parents, core_model, override_model, quality_model)
    ranked_parents = sorted(temporal_ids, key=lambda item: _train_rank(development, base_dev[0], dev_parents[item]), reverse=True)[:PARENT_COUNT]
    cells = []
    for parent_rank, parent_id in enumerate(ranked_parents):
        for weight_index, weight in enumerate(WEIGHTS):
            version = FIRST_VERSION + parent_rank * len(WEIGHTS) + weight_index
            streams = tuple(_combine(base, sleeve, weight) for base, sleeve in zip(base_dev, dev_parents[parent_id], strict=True))
            observations = tuple(v47._observe(development, stream, True) for stream in streams)
            cells.append({"version": version, "parent_rank": parent_rank, "parent_id": parent_id, "weight": weight, "streams": streams, "observations": observations, "rank": _rank(observations), "primary": all(_primary(item) for item in observations)})
    total_cells = PRIOR_COMPARISON_CELLS + len(cells)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    for cell in cells:
        historical_streams = tuple(_combine(base, sleeve, cell["weight"]) for base, sleeve in zip(base_hist, hist_parents[cell["parent_id"]], strict=True))
        historical_obs = tuple(v47._observe(historical, stream, True)["historical_2018_2020"] for stream in historical_streams)
        streams, observations = cell["streams"], cell["observations"]
        fold_metrics = {name: [metrics(stream.values[index], stream.benchmark[index], stream.active[index]) for index in folds] for name, stream in zip(("standard", "cost_18bp", "delay_5min_9bp"), streams, strict=True)}
        starts = {}
        for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
            mask = development.masks()["development_all"] & (development.dates >= pd.Timestamp(start))
            starts[start] = metrics(streams[0].values[mask], streams[0].benchmark[mask], streams[0].active[mask])
        w_index = WEIGHTS.index(cell["weight"])
        neighbors = [item for item in cells if item["parent_id"] == cell["parent_id"] and abs(WEIGHTS.index(item["weight"]) - w_index) <= 1]
        neighborhood = sum(item["primary"] for item in neighbors) / len(neighbors)
        oos = observations[0]["development_oos_2024_2025"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * v47._normal_tail(abs(z_score)) * total_cells)
        gates = {"standard_primary": _primary(observations[0]), "cost_18bp_primary": _primary(observations[1]), "delay_5min_primary": _primary(observations[2]), "four_of_five_positive_folds_all_scenarios": all(sum(float(item["annualized_return"]) > 0 for item in values) >= 4 for values in fold_metrics.values()), "all_start_dates_positive": all(float(item["annualized_return"]) > 0 for item in starts.values()), "historical_15pct_mdd_below_20pct_all_scenarios": all(float(item["annualized_return"]) >= 0.15 and float(item["max_drawdown"]) < 0.20 for item in historical_obs), "parameter_neighborhood_70pct_primary": neighborhood >= 0.70, "consumed_2026q1_above_5pct": float(observations[0]["consumed_2026q1"]["total_return"]) > 0.05, "consumed_2026_total_above_5pct": float(observations[0]["consumed_2026_all"]["total_return"]) > 0.05, "cumulative_bonferroni_5pct": bonferroni < 0.05}
        definition = {"version": cell["version"], "mechanism": "v4513_temporal_diversification", "base_candidate": "lev-v4513-0d708bbd918157bb", "temporal_parent": cell["parent_id"], "temporal_parent_train_rank": cell["parent_rank"], "temporal_weight": cell["weight"], "base_weight": 1 - cell["weight"]}
        records.append({"candidate_id": f"lev-v{cell['version']}-" + _identity(definition), "definition": definition, "standard": observations[0], "cost_18bp": observations[1], "delay_5min_9bp": observations[2], "historical_scenarios": {"standard": historical_obs[0], "cost_18bp": historical_obs[1], "delay_5min_9bp": historical_obs[2]}, "development_folds": fold_metrics, "start_date_stress": starts, "neighbor_primary_share": neighborhood, "multiple_comparison": {"total_cells": total_cells, "z_score": z_score, "bonferroni_p": bonferroni}, "gates": gates, "strict_pre_factory_null_pass": all(gates.values())})
    records.sort(key=lambda item: _rank((item["standard"], item["cost_18bp"], item["delay_5min_9bp"])), reverse=True)
    payload = {"schema_version": "1.0.0", "status": "COMPLETE", "version_range": [FIRST_VERSION, LAST_VERSION], "evaluated_cells": len(cells), "comparison_cells": total_cells, "selected_temporal_parents": ranked_parents, "strict_pre_factory_null_passes": sum(item["strict_pre_factory_null_pass"] for item in records), "elapsed_seconds": time.perf_counter() - started, "records": records}
    v34.v12._atomic(args.output, payload)
    print(json.dumps({"status": "COMPLETE", "evaluated_cells": len(cells), "strict_pre_factory_null_passes": payload["strict_pre_factory_null_passes"], "best": records[0]["candidate_id"], "elapsed_seconds": payload["elapsed_seconds"]}))


if __name__ == "__main__":
    main()
