"""v6070-v6169 sequential non-overlapping sector-flow sleeve campaign."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import time
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v47_score_slope as v47
import numpy as np
import pandas as pd
from evaluate_full_universe_intraday_v5970_v6069_sector_flow_leadership import (
    SectorFlowLeadershipCube,
)

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 6070
LAST_VERSION = 6169
PRIOR_COMPARISON_CELLS = 254_705
STANDARD_COST = 0.0009
STRESS_COST = 0.0018
ASSETS = (3, 4)
SCHEDULE = (
    {"name": "post_open", "decision": 17, "exit": 29, "assets": ASSETS},
    {"name": "late_morning", "decision": 32, "exit": 44, "assets": ASSETS},
    {"name": "midday", "decision": 47, "exit": 59, "assets": ASSETS},
    {"name": "afternoon", "decision": 62, "exit": 77, "assets": ASSETS},
)
QUANTILES = (0.50, 0.60, 0.70, 0.80, 0.90)
ALPHAS = (10.0, 100.0)
FACTOR_SETS = {
    "trend_sector_flow": (
        "current_return",
        "relative_return",
        "path_efficiency",
        "sector_signed_flow_breadth",
        "sector_return_flow_agreement",
    ),
    "rotation_leadership": (
        "current_return",
        "growth_minus_defensive_return",
        "growth_minus_defensive_flow",
        "sector_leadership_spread",
        "sector_leadership_concentration",
    ),
    "broadening_breakout": (
        "current_return",
        "return_acceleration",
        "sector_breadth_acceleration",
        "sector_signed_flow_breadth",
        "sector_path_efficiency_breadth",
    ),
    "contraction_release": (
        "recent_volatility_ratio",
        "return_acceleration",
        "sector_volatility_contraction",
        "sector_breadth_acceleration",
        "sector_return_flow_agreement",
    ),
    "relative_flow": (
        "relative_return",
        "signed_volume_imbalance",
        "volume_acceleration",
        "growth_minus_defensive_flow",
        "sector_flow_dispersion",
    ),
    "reclaim_with_participation": (
        "drawdown_from_high",
        "rebound_from_low",
        "return_acceleration",
        "sector_signed_flow_breadth",
        "sector_breadth_acceleration",
    ),
    "efficient_leadership": (
        "path_efficiency",
        "intraday_range_position",
        "sector_path_efficiency_breadth",
        "sector_leadership_spread",
        "sector_return_flow_agreement",
    ),
    "growth_risk_state": (
        "relative_return",
        "growth_minus_defensive_return",
        "growth_minus_defensive_flow",
        "spy_current",
        "qqq_minus_iwm",
    ),
    "flow_structure": (
        "vwap_distance",
        "close_location",
        "signed_volume_imbalance",
        "sector_flow_dispersion",
        "sector_return_flow_agreement",
    ),
    "balanced": (
        "current_return",
        "relative_return",
        "path_efficiency",
        "return_acceleration",
        "signed_volume_imbalance",
        "sector_signed_flow_breadth",
        "sector_breadth_acceleration",
        "sector_volatility_contraction",
        "growth_minus_defensive_return",
        "growth_minus_defensive_flow",
        "sector_leadership_spread",
    ),
}


def specifications() -> list[tuple[str, float, float]]:
    return list(itertools.product(FACTOR_SETS, QUANTILES, ALPHAS))


def _identity(definition: dict) -> str:
    encoded = json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _fit_models(cube, factors, quantile, alpha):
    train = cube.masks()["train_2022_2023"]
    models = []
    for specification in SCHEDULE:
        matrix, label, finite = v34._matrix(cube, specification, factors)
        selected = train[:, None] & finite
        values, target = matrix[selected], label[selected]
        mean, scale = values.mean(axis=0), values.std(axis=0)
        scale[scale < 1e-8] = 1.0
        standardized = (values - mean) / scale
        coefficients = np.linalg.solve(
            standardized.T @ standardized + alpha * np.eye(len(factors)),
            standardized.T @ target,
        )
        prediction = np.einsum("saf,f->sa", (matrix - mean) / scale, coefficients)
        prediction = np.where(np.isfinite(matrix).all(axis=2), prediction, -np.inf)
        best = np.max(prediction, axis=1)
        threshold = float(np.quantile(best[train & np.isfinite(best)], quantile))
        models.append(v34.Model(dict(specification), factors, mean, scale, coefficients, threshold))
    return models


def _streams(cube, models):
    return (
        v34._stream(cube, models, STANDARD_COST, 0),
        v34._stream(cube, models, STRESS_COST, 0),
        v34._stream(cube, models, STANDARD_COST, 1),
    )


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
        min(
            float(item["development_oos_2024_2025"]["annualized_return"])
            for item in observations
        ),
        min(
            float(item["development_oos_2024_2025"]["information_ratio"])
            for item in observations
        ),
    )


def _serialize_models(models):
    return [
        {
            "specification": model.specification,
            "factors": model.factors,
            "mean": model.mean.tolist(),
            "scale": model.scale.tolist(),
            "coefficients": model.coefficients.tolist(),
            "threshold": model.threshold,
        }
        for model in models
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = SectorFlowLeadershipCube(args.root, "alpaca", 0)
    historical = SectorFlowLeadershipCube(args.root, "historical", 0)
    cells = []
    for offset, (family, quantile, alpha) in enumerate(specifications()):
        models = _fit_models(development, FACTOR_SETS[family], quantile, alpha)
        streams = _streams(development, models)
        observations = tuple(v47._observe(development, stream, True) for stream in streams)
        cells.append(
            {
                "version": FIRST_VERSION + offset,
                "family": family,
                "quantile": quantile,
                "alpha": alpha,
                "models": models,
                "streams": streams,
                "observations": observations,
                "primary": all(_primary(item) for item in observations),
            }
        )
    total_cells = PRIOR_COMPARISON_CELLS + len(cells)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    for cell in cells:
        historical_streams = _streams(historical, cell["models"])
        historical_obs = tuple(
            v47._observe(historical, stream, True)["historical_2018_2020"]
            for stream in historical_streams
        )
        streams, observations = cell["streams"], cell["observations"]
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
            starts[start] = metrics(
                streams[0].values[mask], streams[0].benchmark[mask], streams[0].active[mask]
            )
        q_index = QUANTILES.index(cell["quantile"])
        a_index = ALPHAS.index(cell["alpha"])
        neighbors = [
            item
            for item in cells
            if item["family"] == cell["family"]
            and abs(QUANTILES.index(item["quantile"]) - q_index)
            + abs(ALPHAS.index(item["alpha"]) - a_index)
            <= 1
        ]
        neighborhood = sum(item["primary"] for item in neighbors) / len(neighbors)
        oos = observations[0]["development_oos_2024_2025"]
        z_score = float(oos["information_ratio"]) * math.sqrt(
            max(1, int(oos["trades"])) / 252
        )
        bonferroni = min(
            1.0, 2.0 * v47._normal_tail(abs(z_score)) * total_cells
        )
        gates = {
            "standard_primary": _primary(observations[0]),
            "cost_18bp_primary": _primary(observations[1]),
            "delay_5min_primary": _primary(observations[2]),
            "four_of_five_positive_folds_all_scenarios": all(
                sum(float(item["annualized_return"]) > 0 for item in values) >= 4
                for values in fold_metrics.values()
            ),
            "all_start_dates_positive": all(
                float(item["annualized_return"]) > 0 for item in starts.values()
            ),
            "historical_15pct_mdd_below_20pct_all_scenarios": all(
                float(item["annualized_return"]) >= 0.15
                and float(item["max_drawdown"]) < 0.20
                for item in historical_obs
            ),
            "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
            "consumed_2026q1_above_5pct": float(
                observations[0]["consumed_2026q1"]["total_return"]
            )
            > 0.05,
            "consumed_2026_total_above_5pct": float(
                observations[0]["consumed_2026_all"]["total_return"]
            )
            > 0.05,
            "cumulative_bonferroni_5pct": bonferroni < 0.05,
        }
        definition = {
            "version": cell["version"],
            "mechanism": "sequential_nonoverlapping_sector_flow",
            "factor_set": cell["family"],
            "score_quantile": cell["quantile"],
            "ridge_alpha": cell["alpha"],
            "schedule": SCHEDULE,
        }
        records.append(
            {
                "candidate_id": f"lev-v{cell['version']}-" + _identity(definition),
                "definition": definition,
                "models": _serialize_models(cell["models"]),
                "standard": observations[0],
                "cost_18bp": observations[1],
                "delay_5min_9bp": observations[2],
                "historical_scenarios": dict(
                    zip(
                        ("standard", "cost_18bp", "delay_5min_9bp"),
                        historical_obs,
                        strict=True,
                    )
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
        "evaluated_cells": len(cells),
        "comparison_cells": total_cells,
        "elapsed_seconds": time.perf_counter() - started,
        "strict_pre_factory_null_passes": sum(
            item["strict_pre_factory_null_pass"] for item in records
        ),
        "records": records,
    }
    v34.v12._atomic(args.output, payload)
    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "evaluated_cells": len(cells),
                "strict_pre_factory_null_passes": payload[
                    "strict_pre_factory_null_passes"
                ],
                "best": records[0]["candidate_id"],
                "elapsed_seconds": payload["elapsed_seconds"],
            }
        )
    )


if __name__ == "__main__":
    main()
