"""v5970-v5994: four non-overlapping intraday alpha sleeves.

Each version is an economic allocation of two factor mechanisms across four
causal time slots. Quantile and daily risk target are cells, not versions.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import time
from collections import Counter
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v42_multifactor_vol_target as v42
import evaluate_full_universe_intraday_v47_score_slope as v47
import evaluate_full_universe_intraday_v4670_v5669_residual_alpha as residual
import numpy as np
import pandas as pd
from evaluate_full_universe_intraday_v1463_v1562_intraday_path_multifactor import IntradayPathCube

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 5970
LAST_VERSION = 5994
PRIOR_COMPARISON_CELLS = 254_605
SLOTS = ((2, 17), (18, 35), (36, 53), (54, 72))
MOTIFS = (
    "trend_flow_state",
    "trend_structure",
    "reclaim_flow",
    "contraction_breakout",
    "relative_leadership",
)
QUANTILES = (0.30, 0.40, 0.50, 0.60, 0.70)
TARGETS = (0.25, 0.35)
ALPHA = 100.0


def specifications():
    return list(itertools.product(MOTIFS, MOTIFS))


def _identity(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def assignment(first, second):
    return (first, second, second, first)


def _sum_streams(streams):
    return v34.v12.ReturnStream(
        sum((item.values for item in streams), start=np.zeros(len(streams[0].values))),
        sum((item.benchmark for item in streams), start=np.zeros(len(streams[0].benchmark))),
        np.logical_or.reduce([item.active for item in streams]),
        sum(
            (item.component_trades for item in streams),
            start=np.zeros(len(streams[0].component_trades), dtype=int),
        ),
    )


def _scenario(cube, models, cost, delay, target):
    combined = _sum_streams([residual._raw(cube, model, cost, delay) for model in models])
    exposure = v42._exposure(combined.values, 20, target, 0.0)
    return v42._scaled(combined, exposure)


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
        min(float(item["development_oos_2024_2025"]["annualized_return"]) for item in observations),
        min(float(item["development_oos_2024_2025"]["information_ratio"]) for item in observations),
        min(float(item["development_oos_2024_2025"]["max_drawdown"]) * -1 for item in observations),
    )


def _failed(records):
    return Counter(
        name for record in records for name, passed in record["gates"].items() if not passed
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = IntradayPathCube(args.root, "alpaca", 0)
    historical = IntradayPathCube(args.root, "historical", 0)
    model_cache = {}
    for family, slot, quantile in itertools.product(MOTIFS, SLOTS, QUANTILES):
        model_cache[(family, slot, quantile)] = residual._fit(
            development, family, slot, quantile, ALPHA
        )
    cells_by_version = {}
    for offset, (first, second) in enumerate(specifications()):
        version = FIRST_VERSION + offset
        cells = []
        families = assignment(first, second)
        for quantile, target in itertools.product(QUANTILES, TARGETS):
            models = tuple(
                model_cache[(family, slot, quantile)]
                for family, slot in zip(families, SLOTS, strict=True)
            )
            streams = tuple(
                _scenario(development, models, cost, delay, target)
                for cost, delay in (
                    (v34.STANDARD_COST, 0),
                    (v34.STRESS_COST, 0),
                    (v34.STANDARD_COST, 1),
                )
            )
            observations = tuple(v47._observe(development, stream, True) for stream in streams)
            cells.append(
                {
                    "version": version,
                    "first": first,
                    "second": second,
                    "quantile": quantile,
                    "target": target,
                    "models": models,
                    "streams": streams,
                    "observations": observations,
                    "rank": _rank(observations),
                    "primary": all(_primary(item) for item in observations),
                }
            )
        cells_by_version[version] = cells
    total_cells = PRIOR_COMPARISON_CELLS + sum(map(len, cells_by_version.values()))
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    for version, cells in cells_by_version.items():
        selected = max(cells, key=lambda item: item["rank"])
        historical_streams = tuple(
            _scenario(historical, selected["models"], cost, delay, selected["target"])
            for cost, delay in (
                (v34.STANDARD_COST, 0),
                (v34.STRESS_COST, 0),
                (v34.STANDARD_COST, 1),
            )
        )
        historical_obs = tuple(
            v47._observe(historical, stream, True)["historical_2018_2020"]
            for stream in historical_streams
        )
        streams, observations = selected["streams"], selected["observations"]
        fold_metrics = {
            name: [
                metrics(stream.values[index], stream.benchmark[index], stream.active[index])
                for index in folds
            ]
            for name, stream in zip(
                ("standard", "cost_18bp", "delay_5min_9bp"), streams, strict=True
            )
        }
        starts = {}
        for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
            mask = development.masks()["development_all"] & (
                development.dates >= pd.Timestamp(start)
            )
            starts[start] = {
                name: metrics(stream.values[mask], stream.benchmark[mask], stream.active[mask])
                for name, stream in zip(
                    ("standard", "cost_18bp", "delay_5min_9bp"), streams, strict=True
                )
            }
        q_index, t_index = QUANTILES.index(selected["quantile"]), TARGETS.index(selected["target"])
        neighbors = [
            cell
            for cell in cells
            if abs(QUANTILES.index(cell["quantile"]) - q_index)
            + abs(TARGETS.index(cell["target"]) - t_index)
            <= 1
        ]
        neighborhood = sum(cell["primary"] for cell in neighbors) / len(neighbors)
        oos = observations[0]["development_oos_2024_2025"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * v47._normal_tail(abs(z_score)) * total_cells)
        gates = {
            "standard_primary": _primary(observations[0]),
            "cost_18bp_primary": _primary(observations[1]),
            "delay_5min_primary": _primary(observations[2]),
            "four_of_five_positive_folds_all_scenarios": all(
                sum(float(x["annualized_return"]) > 0 for x in values) >= 4
                for values in fold_metrics.values()
            ),
            "all_start_dates_positive_all_scenarios": all(
                float(item["annualized_return"]) > 0
                for values in starts.values()
                for item in values.values()
            ),
            "historical_15pct_mdd_below_20pct_all_scenarios": all(
                float(item["annualized_return"]) >= 0.15 and float(item["max_drawdown"]) < 0.20
                for item in historical_obs
            ),
            "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
            "consumed_2026q1_above_5pct": float(observations[0]["consumed_2026q1"]["total_return"])
            > 0.05,
            "consumed_2026_total_above_5pct": float(
                observations[0]["consumed_2026_all"]["total_return"]
            )
            > 0.05,
            "cumulative_bonferroni_5pct": bonferroni < 0.05,
        }
        definition = {
            "version": version,
            "mechanism": "four_slot_intraday_alpha_ensemble",
            "slot_assignment": [
                {"decision": d, "exit": e, "factor_family": f}
                for (d, e), f in zip(
                    SLOTS, assignment(selected["first"], selected["second"]), strict=True
                )
            ],
            "score_quantile": selected["quantile"],
            "daily_target_volatility": selected["target"],
            "lookback": 20,
            "ridge_alpha": ALPHA,
            "gross_limit_each_nonoverlapping_slot": 1.0,
        }
        records.append(
            {
                "candidate_id": f"lev-v{version}-" + _identity(definition),
                "definition": definition,
                "models": [
                    {
                        "factors": model.factors,
                        "mean": model.mean.tolist(),
                        "scale": model.scale.tolist(),
                        "coefficients": model.coefficients.tolist(),
                        "threshold": model.threshold,
                    }
                    for model in selected["models"]
                ],
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
        key=lambda item: _rank((item["standard"], item["cost_18bp"], item["delay_5min_9bp"])),
        reverse=True,
    )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version_range": [FIRST_VERSION, LAST_VERSION],
        "versions": len(specifications()),
        "evaluated_cells": sum(map(len, cells_by_version.values())),
        "comparison_cells": total_cells,
        "strict_pre_factory_null_passes": sum(
            item["strict_pre_factory_null_pass"] for item in records
        ),
        "rejection_reason_counts": dict(_failed(records)),
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
