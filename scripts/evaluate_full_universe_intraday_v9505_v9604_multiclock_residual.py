"""v9505-v9604: causal three-clock residual portfolios.

Each version is a distinct factor family and a distinct sequence of three
non-overlapping intraday holding windows. Parameter cells stay within the
version and never masquerade as extra strategy versions.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v39_multifactor_regime_gate as v39
import evaluate_full_universe_intraday_v4670_v5669_residual_alpha as residual
import evaluate_full_universe_intraday_v5970_v6069_sector_flow_leadership as sector
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 9505
LAST_VERSION = 9604
PRIOR_COMPARISON_CELLS = 283_783
QUANTILES = (0.60, 0.70, 0.80)
ALPHAS = (100.0, 1000.0)

FACTOR_BUNDLES = (
    ("gap_flow_residual", ("gap", "relative_return", "signed_volume_imbalance", "close_location")),
    ("efficient_relative_leader", ("relative_return", "path_efficiency", "trend_consistency", "close_location")),
    ("vwap_flow_confirmation", ("vwap_distance", "signed_volume_imbalance", "sector_return_flow_agreement")),
    ("quiet_sector_breakout", ("relative_return", "recent_volatility_ratio", "sector_volatility_contraction", "sector_breadth")),
    ("range_flow_position", ("intraday_range_position", "rebound_from_low", "signed_volume_imbalance", "volume_acceleration")),
    ("residual_sector_rotation", ("leverage_residual", "sector_leadership_spread", "growth_minus_defensive_flow")),
    ("rank_breadth_persistence", ("current_rank", "sector_breadth", "sector_breadth_acceleration", "path_efficiency")),
    ("cross_asset_confirmation", ("relative_return", "qqq_minus_iwm", "risk_asset_agreement", "tech_minus_market")),
    ("liquidity_absorption_path", ("signed_volume_imbalance", "volume_acceleration", "range_ratio", "path_efficiency")),
    ("balanced_multiclock", ("current_return", "relative_return", "vwap_distance", "close_location", "signed_volume_imbalance", "sector_breadth")),
)

WINDOW_STRUCTURES = (
    ((2, 11), (11, 23), (23, 35)),
    ((2, 11), (11, 23), (35, 47)),
    ((2, 11), (17, 29), (35, 47)),
    ((5, 17), (17, 29), (29, 41)),
    ((5, 17), (17, 29), (41, 53)),
    ((5, 17), (23, 35), (41, 53)),
    ((11, 23), (23, 35), (35, 47)),
    ((11, 23), (29, 41), (47, 59)),
    ((17, 29), (29, 41), (53, 65)),
    ((2, 17), (23, 41), (47, 65)),
)


def specifications() -> list[tuple]:
    return [(family, windows) for windows in WINDOW_STRUCTURES for family in FACTOR_BUNDLES]


def _combine(streams):
    return v34.v12.ReturnStream(
        np.sum([item.values for item in streams], axis=0),
        np.sum([item.benchmark for item in streams], axis=0),
        np.logical_or.reduce([item.active for item in streams]),
        np.sum([item.component_trades for item in streams], axis=0),
    )


def _scenario_streams(cube, models):
    sleeves = [residual._streams(cube, model) for model in models]
    return tuple(_combine([sleeve[index] for sleeve in sleeves]) for index in range(3))


def _primary(observation):
    oos = observation["development_oos_2024_2025"]
    return (
        float(oos["annualized_return"]) >= 0.50
        and float(oos["max_drawdown"]) < 0.20
        and float(oos["information_ratio"]) >= 1.0
        and all(float(observation[name]["annualized_return"]) > 0 for name in ("train_2022_2023", "2024", "2025"))
    )


def _rank(observations):
    return (
        min(float(item["development_oos_2024_2025"]["annualized_return"]) for item in observations),
        min(float(item["development_oos_2024_2025"]["information_ratio"]) for item in observations),
    )


def _model_dict(model):
    return {
        "family": model.family,
        "factors": list(model.factors),
        "decision": model.decision,
        "exit_bar": model.exit_bar,
        "quantile": model.quantile,
        "alpha": model.alpha,
        "mean": model.mean.tolist(),
        "scale": model.scale.tolist(),
        "coefficients": model.coefficients.tolist(),
        "threshold": model.threshold,
    }


def _cells(development, historical, family, windows):
    family_name, factors = family
    residual.FACTOR_SETS[family_name] = factors
    cells = []
    for quantile in QUANTILES:
        for alpha in ALPHAS:
            models = tuple(residual._fit(development, family_name, window, quantile, alpha) for window in windows)
            streams = _scenario_streams(development, models)
            historical_streams = _scenario_streams(historical, models)
            observations = tuple(v39._observe(development, stream, True) for stream in streams)
            historical_observations = tuple(v39._observe(historical, stream, True)["historical_2018_2020"] for stream in historical_streams)
            cells.append({
                "parameters": {"factor_family": family_name, "windows": [list(item) for item in windows], "score_quantile": quantile, "ridge_alpha": alpha},
                "models": [_model_dict(model) for model in models],
                "streams": streams,
                "observations": observations,
                "historical": historical_observations,
                "primary": all(_primary(item) for item in observations),
                "rank": _rank(observations),
            })
    return cells


def _neighbor_share(cells, selected):
    q_index = QUANTILES.index(selected["parameters"]["score_quantile"])
    a_index = ALPHAS.index(selected["parameters"]["ridge_alpha"])
    neighbors = [
        item for item in cells
        if abs(QUANTILES.index(item["parameters"]["score_quantile"]) - q_index)
        + abs(ALPHAS.index(item["parameters"]["ridge_alpha"]) - a_index) <= 1
    ]
    return sum(item["primary"] for item in neighbors) / len(neighbors)


def _record(development, version, cells, selected, total_cells):
    names = ("standard", "cost_18bp", "delay_5min_9bp")
    observations = selected["observations"]
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    fold_metrics = {
        name: [metrics(stream.values[index], stream.benchmark[index], stream.active[index]) for index in folds]
        for name, stream in zip(names, selected["streams"], strict=True)
    }
    starts = {}
    for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
        mask = development.masks()["development_all"] & (development.dates >= pd.Timestamp(start))
        starts[start] = {
            name: metrics(stream.values[mask], stream.benchmark[mask], stream.active[mask])
            for name, stream in zip(names, selected["streams"], strict=True)
        }
    neighborhood = _neighbor_share(cells, selected)
    oos = observations[0]["development_oos_2024_2025"]
    z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
    bonferroni = min(1.0, 2.0 * v39._normal_tail(abs(z_score)) * total_cells)
    gates = {
        "standard_primary": _primary(observations[0]),
        "cost_18bp_primary": _primary(observations[1]),
        "delay_5min_primary": _primary(observations[2]),
        "four_of_five_positive_folds_all_scenarios": all(sum(float(item["annualized_return"]) > 0 for item in values) >= 4 for values in fold_metrics.values()),
        "all_start_dates_positive_all_scenarios": all(float(metric["annualized_return"]) > 0 for scenarios in starts.values() for metric in scenarios.values()),
        "historical_15pct_mdd_below_20pct_all_scenarios": all(float(item["annualized_return"]) >= 0.15 and float(item["max_drawdown"]) < 0.20 for item in selected["historical"]),
        "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
        "consumed_2026q1_above_5pct": float(observations[0]["consumed_2026q1"]["total_return"]) > 0.05,
        "consumed_2026_total_above_5pct": float(observations[0]["consumed_2026_all"]["total_return"]) > 0.05,
        "cumulative_bonferroni_5pct": bonferroni < 0.05,
    }
    definition = {"version": version, **selected["parameters"], "gross_max": 1.0, "overnight": False}
    return {
        "candidate_id": f"lev-v{version}-" + residual._identity(definition),
        "definition": definition,
        "models": selected["models"],
        "development_rank": list(selected["rank"]),
        **{name: observation for name, observation in zip(names, observations, strict=True)},
        "historical_scenarios": {name: observation for name, observation in zip(names, selected["historical"], strict=True)},
        "development_folds": fold_metrics,
        "start_date_stress": starts,
        "neighbor_primary_share": neighborhood,
        "multiple_comparison": {"total_cells": total_cells, "z_score": z_score, "bonferroni_p": bonferroni},
        "gates": gates,
        "pre_factory_null_pass": all(gates.values()),
        "all_reference_gates_pass": all(gates.values()),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = sector.SectorFlowLeadershipCube(args.root, "alpaca", 0)
    historical = sector.SectorFlowLeadershipCube(args.root, "historical", 0)
    specs = specifications()
    planned_cells = len(specs) * len(QUANTILES) * len(ALPHAS)
    total_cells = PRIOR_COMPARISON_CELLS + planned_cells
    if len(specs) != 100 or planned_cells != 600:
        raise RuntimeError("V9505_V9604_PREREGISTRATION_MISMATCH")
    all_records, versions = [], []
    for offset, (family, windows) in enumerate(specs):
        version = FIRST_VERSION + offset
        version_started = time.perf_counter()
        path = args.output_dir / f"full-universe-intraday-v{version}-exact.json"
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            records = payload["records"]
        else:
            cells = _cells(development, historical, family, windows)
            cells.sort(key=lambda item: item["rank"], reverse=True)
            records = [_record(development, version, cells, item, total_cells) for item in cells[:3]]
            payload = {
                "schema_version": "1.0.0",
                "status": "COMPLETE",
                "version": version,
                "economic_hypothesis": f"{family[0]} sequentially over {windows}",
                "scan": {"evaluated_cells": len(cells), "frozen_frontier": 3, "elapsed_seconds": time.perf_counter() - version_started},
                "pre_factory_null_hits": sum(item["pre_factory_null_pass"] for item in records),
                "records": records,
            }
            v34.v12._atomic(path, payload)
        all_records.extend(records)
        versions.append({
            "version": version,
            "hypothesis": payload["economic_hypothesis"],
            "cells": payload["scan"]["evaluated_cells"],
            "pre_factory_null_hits": payload["pre_factory_null_hits"],
            "best_candidate_id": records[0]["candidate_id"],
            "best_oos_annualized_return": records[0]["standard"]["development_oos_2024_2025"]["annualized_return"],
            "best_consumed_2026_total_return": records[0]["standard"]["consumed_2026_all"]["total_return"],
        })
        failures = Counter(name for record in all_records for name, passed in record["gates"].items() if not passed)
        summary = {
            "schema_version": "1.0.0",
            "status": "COMPLETE" if version == LAST_VERSION else "RUNNING",
            "version_range": [FIRST_VERSION, LAST_VERSION],
            "completed_versions": offset + 1,
            "planned_versions": 100,
            "planned_new_cells": planned_cells,
            "cumulative_comparison_cells": total_cells,
            "pre_factory_null_hits": sum(item["pre_factory_null_pass"] for item in all_records),
            "rejected_frontier_records": len(all_records) - sum(item["pre_factory_null_pass"] for item in all_records),
            "rejection_reason_counts": dict(failures),
            "elapsed_seconds": time.perf_counter() - started,
            "versions": versions,
        }
        v34.v12._atomic(args.summary, summary)
        print(json.dumps({"progress": f"{offset + 1}/100", **versions[-1]}), flush=True)


if __name__ == "__main__":
    main()
