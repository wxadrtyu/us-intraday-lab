"""Preregistered diversified ensembles over frozen v42 parents."""

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
import evaluate_full_universe_intraday_v4070_v4169_state_routed_v42 as prior
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 4270
LAST_VERSION = 4369
PRIOR_COMPARISON_CELLS = 252_905
SOURCE_SHA256 = prior.SOURCE_SHA256
COUNTS = (2, 3, 4, 5, 6)
PENALTIES = (0.0, 0.25, 0.50, 0.75, 1.0)
WEIGHTINGS = ("equal", "inverse_train_volatility")
POOLS = ("development_frontier_100", "all_500")
MECHANISM = "train_stability_correlation_greedy_ensemble"


def specifications():
    return list(itertools.product(COUNTS, PENALTIES, WEIGHTINGS, POOLS))


def _identity(definition: dict) -> str:
    return hashlib.sha256(json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def _weights(streams, train: np.ndarray, weighting: str) -> np.ndarray:
    if weighting == "equal":
        return np.full(len(streams), 1.0 / len(streams))
    vol = np.asarray([np.std(stream.values[train], ddof=1) for stream in streams])
    inverse = np.divide(1.0, vol, out=np.zeros_like(vol), where=vol > 1e-10)
    return inverse / inverse.sum()


def _combine(streams, weights: np.ndarray):
    values = sum(weight * stream.values for weight, stream in zip(weights, streams, strict=True))
    benchmark = sum(weight * stream.benchmark for weight, stream in zip(weights, streams, strict=True))
    active = np.logical_or.reduce([stream.active for stream in streams])
    trades = sum(stream.component_trades for stream in streams)
    return v34.v12.ReturnStream(values, benchmark, active, trades)


def _selection_score(cube, stream, penalty: float, max_correlation: float) -> float:
    masks = cube.masks()
    observations = [metrics(stream.values[masks[name]], stream.benchmark[masks[name]], stream.active[masks[name]]) for name in ("train_2022_2023", "2024", "2025")]
    return min(float(item["annualized_return"]) for item in observations) + 0.10 * min(float(item["information_ratio"]) for item in observations) - penalty * max_correlation


def _greedy(cube, parent_ids, standard_streams, count: int, penalty: float, weighting: str):
    train = cube.masks()["train_2022_2023"]
    selected = []
    remaining = list(parent_ids)
    while len(selected) < count:
        best = None
        for candidate_id in remaining:
            trial_ids = [*selected, candidate_id]
            trial_streams = [standard_streams[item] for item in trial_ids]
            weights = _weights(trial_streams, train, weighting)
            combined = _combine(trial_streams, weights)
            if not selected:
                correlation = 0.0
            else:
                candidate = standard_streams[candidate_id].values[train]
                correlations = []
                for item in selected:
                    other = standard_streams[item].values[train]
                    corr = np.corrcoef(candidate, other)[0, 1]
                    correlations.append(abs(float(corr)) if np.isfinite(corr) else 1.0)
                correlation = max(correlations)
            score = _selection_score(cube, combined, penalty, correlation)
            if best is None or score > best[0]:
                best = (score, candidate_id)
        selected.append(best[1])
        remaining.remove(best[1])
    return tuple(selected)


def _primary(observation: dict) -> bool:
    oos = observation["development_oos_2024_2025"]
    return float(oos["annualized_return"]) >= 0.50 and float(oos["max_drawdown"]) < 0.20 and float(oos["information_ratio"]) >= 1.0 and all(float(observation[name]["annualized_return"]) > 0 for name in ("train_2022_2023", "2024", "2025"))


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
    parents = source["records"]
    if len(parents) != 500 or len(specifications()) != 100:
        raise RuntimeError("ENSEMBLE_PREREGISTRATION_MISMATCH")
    development = v34.Cube(args.root, "alpaca", 0)
    historical = v34.Cube(args.root, "historical", 0)
    models = {item["candidate_id"]: v39._models(development, [item["definition"]["strategy"]])[0] for item in parents}
    dev_streams = {item["candidate_id"]: prior._parent_streams(development, item, models[item["candidate_id"]]) for item in parents}
    hist_streams = {item["candidate_id"]: prior._parent_streams(historical, item, models[item["candidate_id"]]) for item in parents}
    parent_ids = [item["candidate_id"] for item in parents]
    standard_streams = {candidate_id: dev_streams[candidate_id][0] for candidate_id in parent_ids}
    train = development.masks()["train_2022_2023"]
    records = []
    total_cells = PRIOR_COMPARISON_CELLS + len(specifications())
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    for offset, (count, penalty, weighting, pool) in enumerate(specifications()):
        available = parent_ids[:100] if pool == "development_frontier_100" else parent_ids
        selected = _greedy(development, available, standard_streams, count, penalty, weighting)
        selected_dev = [[dev_streams[candidate_id][scenario] for candidate_id in selected] for scenario in range(3)]
        weights = _weights(selected_dev[0], train, weighting)
        streams = tuple(_combine(items, weights) for items in selected_dev)
        observations = tuple(v47._observe(development, stream, True) for stream in streams)
        historical_combined = tuple(_combine([hist_streams[candidate_id][scenario] for candidate_id in selected], weights) for scenario in range(3))
        historical_obs = tuple(v47._observe(historical, stream, True)["historical_2018_2020"] for stream in historical_combined)
        fold_metrics = {name: [metrics(stream.values[index], stream.benchmark[index], stream.active[index]) for index in folds] for name, stream in zip(("standard", "cost_18bp", "delay_5min_9bp"), streams, strict=True)}
        starts = {}
        for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
            mask = development.masks()["development_all"] & (development.dates >= pd.Timestamp(start))
            starts[start] = metrics(streams[0].values[mask], streams[0].benchmark[mask], streams[0].active[mask])
        oos = observations[0]["development_oos_2024_2025"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * v47._normal_tail(abs(z_score)) * total_cells)
        definition = {"version": FIRST_VERSION + offset, "mechanism": MECHANISM, "component_count": count, "correlation_penalty": penalty, "weighting": weighting, "pool": pool, "selected_parents": selected, "weights": weights.tolist()}
        records.append({
            "candidate_id": f"lev-v{FIRST_VERSION + offset}-" + _identity(definition), "definition": definition,
            "standard": observations[0], "cost_18bp": observations[1], "delay_5min_9bp": observations[2],
            "historical_scenarios": {"standard": historical_obs[0], "cost_18bp": historical_obs[1], "delay_5min_9bp": historical_obs[2]},
            "development_folds": fold_metrics, "start_date_stress": starts,
            "multiple_comparison": {"total_cells": total_cells, "z_score": z_score, "bonferroni_p": bonferroni},
        })
    for record in records:
        d = record["definition"]
        k_index, p_index = COUNTS.index(d["component_count"]), PENALTIES.index(d["correlation_penalty"])
        neighbors = [x for x in records if x["definition"]["weighting"] == d["weighting"] and x["definition"]["pool"] == d["pool"] and abs(COUNTS.index(x["definition"]["component_count"]) - k_index) + abs(PENALTIES.index(x["definition"]["correlation_penalty"]) - p_index) <= 1]
        neighborhood = sum(all(_primary(x[name]) for name in ("standard", "cost_18bp", "delay_5min_9bp")) for x in neighbors) / len(neighbors)
        gates = {
            "standard_primary": _primary(record["standard"]), "cost_18bp_primary": _primary(record["cost_18bp"]), "delay_5min_primary": _primary(record["delay_5min_9bp"]),
            "four_of_five_positive_folds_all_scenarios": all(sum(float(x["annualized_return"]) > 0 for x in values) >= 4 for values in record["development_folds"].values()),
            "all_start_dates_positive": all(float(x["annualized_return"]) > 0 for x in record["start_date_stress"].values()),
            "historical_15pct_mdd_below_20pct_all_scenarios": all(float(x["annualized_return"]) >= 0.15 and float(x["max_drawdown"]) < 0.20 for x in record["historical_scenarios"].values()),
            "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
            "consumed_2026q1_above_5pct": float(record["standard"]["consumed_2026q1"]["total_return"]) > 0.05,
            "consumed_2026_total_above_5pct": float(record["standard"]["consumed_2026_all"]["total_return"]) > 0.05,
            "cumulative_bonferroni_5pct": float(record["multiple_comparison"]["bonferroni_p"]) < 0.05,
        }
        record.update({"neighbor_primary_share": neighborhood, "gates": gates, "strict_pre_factory_null_pass": all(gates.values())})
    records.sort(key=lambda x: (min(float(x[name]["development_oos_2024_2025"]["annualized_return"]) for name in ("standard", "cost_18bp", "delay_5min_9bp")), min(float(x[name]["development_oos_2024_2025"]["information_ratio"]) for name in ("standard", "cost_18bp", "delay_5min_9bp"))), reverse=True)
    payload = {"schema_version": "1.0.0", "status": "COMPLETE", "version_range": [FIRST_VERSION, LAST_VERSION], "evaluated_cells": len(records), "comparison_cells": total_cells, "strict_pre_factory_null_passes": sum(x["strict_pre_factory_null_pass"] for x in records), "elapsed_seconds": time.perf_counter() - started, "records": records}
    v34.v12._atomic(args.output, payload)
    print(json.dumps({"status": "COMPLETE", "evaluated_cells": len(records), "strict_pre_factory_null_passes": payload["strict_pre_factory_null_passes"], "best": records[0]["candidate_id"], "elapsed_seconds": payload["elapsed_seconds"]}))


if __name__ == "__main__":
    main()
