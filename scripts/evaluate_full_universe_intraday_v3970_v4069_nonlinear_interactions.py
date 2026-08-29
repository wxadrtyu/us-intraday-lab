"""Preregistered nonlinear multifactor interaction campaign."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import time
from pathlib import Path

import analyze_full_universe_intraday_v53_cross_asset_factors as cross
import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v47_score_slope as v47
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 3970
LAST_VERSION = 4069
PRIOR_COMPARISON_CELLS = 201_805
ASSETS = np.array((3, 4))
SCHEDULES = ((11, 35), (17, 41), (23, 53), (29, 59), (35, 65))
ALPHAS = (1.0, 30.0)
QUANTILES = (0.60, 0.80)
FACTOR_SETS = {
    "rebound_interactions": (
        "current_return", "recent_return", "close_location", "vwap_distance",
        "prior1_return", "prior20_return", "return_acceleration", "realized_volatility",
    ),
    "continuation_interactions": (
        "current_return", "recent_return", "path_efficiency", "trend_consistency",
        "signed_volume_imbalance", "volume_acceleration", "close_location", "gap",
    ),
    "cross_asset_interactions": (
        "current_return", "leverage_residual", "qqq_current", "tech_minus_market",
        "sector_breadth", "sector_dispersion", "risk_asset_agreement", "spy_volatility",
    ),
    "path_flow_interactions": (
        "recent_return", "path_efficiency", "close_location", "range_ratio",
        "realized_volatility", "signed_volume_imbalance", "volume_acceleration", "vwap_distance",
    ),
    "mixed_state_interactions": (
        "current_return", "recent_return", "prior20_return", "leverage_residual",
        "sector_breadth", "spy_current", "realized_volatility", "signed_volume_imbalance",
    ),
}


class NonlinearCube(cross.Cube):
    def factors(self, decision: int) -> dict[str, np.ndarray]:
        output = super().factors(decision)
        if "return_acceleration" in output:
            return output
        returns = self.bar_return[:, : decision + 1, :]
        recent_start = max(1, decision - 3)

        def safe_mean(values: np.ndarray) -> np.ndarray:
            finite = np.isfinite(values)
            count = finite.sum(axis=1)
            return np.divide(
                np.where(finite, values, 0.0).sum(axis=1), count,
                out=np.full_like(output["current_return"], np.nan), where=count > 0,
            )

        output["return_acceleration"] = (
            safe_mean(returns[:, recent_start:, :]) - safe_mean(returns[:, :recent_start, :])
        )
        return output


def specifications() -> list[tuple]:
    return list(itertools.product(SCHEDULES, FACTOR_SETS, ALPHAS, QUANTILES))


def _identity(definition: dict) -> str:
    raw = json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()[:16]


def _features(cube: NonlinearCube, decision: int, names: tuple[str, ...]) -> np.ndarray:
    available = cube.factors(decision)
    return np.stack([available[name][:, ASSETS] for name in names], axis=2)


def _expand(standardized: np.ndarray) -> np.ndarray:
    pieces = [standardized, standardized**2]
    pieces.extend(
        standardized[:, :, left : left + 1] * standardized[:, :, right : right + 1]
        for left in range(standardized.shape[2])
        for right in range(left + 1, standardized.shape[2])
    )
    return np.concatenate(pieces, axis=2)


def _fit(cube: NonlinearCube, definition: dict) -> dict:
    decision, exit_bar = int(definition["decision"]), int(definition["exit"])
    names = tuple(definition["factors"])
    matrix = _features(cube, decision, names)
    entry = decision + 1
    label = cube.opens[:, exit_bar, ASSETS] / cube.opens[:, entry, ASSETS] - 1.0 - v34.STANDARD_COST
    finite = np.isfinite(matrix).all(axis=2) & np.isfinite(label)
    selected = cube.masks()["train_2022_2023"][:, None] & finite
    values, target = matrix[selected], label[selected]
    mean, scale = values.mean(axis=0), values.std(axis=0)
    scale[scale < 1e-8] = 1.0
    expanded = _expand(((values - mean) / scale)[:, None, :])[:, 0, :]
    target_mean = float(target.mean())
    alpha = float(definition["alpha"])
    coefficients = np.linalg.solve(
        expanded.T @ expanded + alpha * np.eye(expanded.shape[1]),
        expanded.T @ (target - target_mean),
    )
    train_prediction = target_mean + expanded @ coefficients
    threshold = float(np.quantile(train_prediction, float(definition["quantile"])))
    return {
        "mean": mean.tolist(), "scale": scale.tolist(), "coefficients": coefficients.tolist(),
        "target_mean": target_mean, "threshold": threshold,
    }


def _stream(cube: NonlinearCube, definition: dict, model: dict, cost: float, delay: int):
    decision, exit_bar = int(definition["decision"]), int(definition["exit"])
    matrix = _features(cube, decision, tuple(definition["factors"]))
    standardized = (matrix - np.asarray(model["mean"])) / np.asarray(model["scale"])
    expanded = _expand(standardized)
    prediction = float(model["target_mean"]) + np.einsum(
        "saf,f->sa", expanded, np.asarray(model["coefficients"])
    )
    prediction = np.where(np.isfinite(matrix).all(axis=2), prediction, -np.inf)
    local = np.argmax(prediction, axis=1)
    selected = ASSETS[local]
    best = prediction[cube.rows, local]
    entry = decision + 1 + delay
    active = np.isfinite(best) & (best >= float(model["threshold"]))
    active &= cube.first[cube.rows, entry, selected] <= entry * 5 + cube.boundary_tolerance
    active &= cube.first[cube.rows, exit_bar, selected] <= exit_bar * 5 + cube.boundary_tolerance
    active &= np.isfinite(cube.opens[cube.rows, entry, selected])
    active &= np.isfinite(cube.opens[cube.rows, exit_bar, selected])
    active &= np.isfinite(cube.opens[:, entry, 0]) & np.isfinite(cube.opens[:, exit_bar, 0])
    values, benchmark = np.zeros(len(cube.sessions)), np.zeros(len(cube.sessions))
    values[active] = (
        cube.opens[cube.rows[active], exit_bar, selected[active]]
        / cube.opens[cube.rows[active], entry, selected[active]] - 1.0 - cost
    )
    benchmark[active] = cube.opens[active, exit_bar, 0] / cube.opens[active, entry, 0] - 1.0
    return v34.v12.ReturnStream(values, benchmark, active, active.astype(int))


def _primary(observation: dict) -> bool:
    oos = observation["development_oos_2024_2025"]
    return (
        float(oos["annualized_return"]) >= 0.50
        and float(oos["max_drawdown"]) < 0.20
        and float(oos["information_ratio"]) >= 1.0
        and all(float(observation[name]["annualized_return"]) > 0 for name in ("train_2022_2023", "2024", "2025"))
    )


def _observations(cube, definition, model):
    streams = (
        _stream(cube, definition, model, v34.STANDARD_COST, 0),
        _stream(cube, definition, model, v34.STRESS_COST, 0),
        _stream(cube, definition, model, v34.STANDARD_COST, 1),
    )
    return streams, tuple(v47._observe(cube, stream, True) for stream in streams)


def _neighbor_share(records: list[dict], record: dict) -> float:
    definition = record["definition"]
    neighbors = [
        item for item in records
        if item["definition"]["decision"] == definition["decision"]
        and item["definition"]["factor_set"] == definition["factor_set"]
    ]
    return sum(item["primary_triplet"] for item in neighbors) / len(neighbors)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    development = NonlinearCube(args.root, "alpaca", 0)
    historical = NonlinearCube(args.root, "historical", 0)
    specs = specifications()
    if len(specs) != 100:
        raise RuntimeError("NONLINEAR_PREREGISTRATION_MISMATCH")
    records = []
    for offset, (schedule, factor_set, alpha, quantile) in enumerate(specs):
        decision, exit_bar = schedule
        definition = {
            "version": FIRST_VERSION + offset, "mechanism": "train_only_quadratic_ridge",
            "decision": decision, "exit": exit_bar, "factor_set": factor_set,
            "factors": FACTOR_SETS[factor_set], "alpha": alpha, "quantile": quantile,
        }
        model = _fit(development, definition)
        streams, observations = _observations(development, definition, model)
        _, historical_observations = _observations(historical, definition, model)
        records.append({
            "candidate_id": f"lev-v{FIRST_VERSION + offset}-" + _identity(definition),
            "definition": definition, "model": model, "streams": streams,
            "standard": observations[0], "cost_18bp": observations[1],
            "delay_5min_9bp": observations[2],
            "historical_scenarios": {
                "standard": historical_observations[0]["historical_2018_2020"],
                "cost_18bp": historical_observations[1]["historical_2018_2020"],
                "delay_5min_9bp": historical_observations[2]["historical_2018_2020"],
            },
            "primary_triplet": all(_primary(item) for item in observations),
        })
    total_cells = PRIOR_COMPARISON_CELLS + len(records)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    for record in records:
        streams = record.pop("streams")
        fold_metrics = {
            name: [metrics(stream.values[index], stream.benchmark[index], stream.active[index]) for index in folds]
            for name, stream in zip(("standard", "cost_18bp", "delay_5min_9bp"), streams, strict=True)
        }
        starts = {}
        for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
            mask = development.masks()["development_all"] & (development.dates >= pd.Timestamp(start))
            starts[start] = metrics(streams[0].values[mask], streams[0].benchmark[mask], streams[0].active[mask])
        neighborhood = _neighbor_share(records, record)
        oos = record["standard"]["development_oos_2024_2025"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * v47._normal_tail(abs(z_score)) * total_cells)
        gates = {
            "standard_primary": _primary(record["standard"]),
            "cost_18bp_primary": _primary(record["cost_18bp"]),
            "delay_5min_primary": _primary(record["delay_5min_9bp"]),
            "four_of_five_positive_folds_all_scenarios": all(
                sum(float(item["annualized_return"]) > 0 for item in values) >= 4 for values in fold_metrics.values()
            ),
            "all_start_dates_positive": all(float(item["annualized_return"]) > 0 for item in starts.values()),
            "historical_15pct_mdd_below_20pct_all_scenarios": all(
                float(item["annualized_return"]) >= 0.15 and float(item["max_drawdown"]) < 0.20
                for item in record["historical_scenarios"].values()
            ),
            "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
            "consumed_2026q1_above_5pct": float(record["standard"]["consumed_2026q1"]["total_return"]) > 0.05,
            "consumed_2026_total_above_5pct": float(record["standard"]["consumed_2026_all"]["total_return"]) > 0.05,
            "cumulative_bonferroni_5pct": bonferroni < 0.05,
        }
        record.update({
            "development_folds": fold_metrics, "start_date_stress": starts,
            "neighbor_primary_share": neighborhood,
            "multiple_comparison": {"total_cells": total_cells, "z_score": z_score, "bonferroni_p": bonferroni},
            "gates": gates, "strict_pre_factory_null_pass": all(gates.values()),
        })
    records.sort(
        key=lambda item: (
            min(float(item[name]["development_oos_2024_2025"]["annualized_return"]) for name in ("standard", "cost_18bp", "delay_5min_9bp")),
            min(float(item[name]["development_oos_2024_2025"]["information_ratio"]) for name in ("standard", "cost_18bp", "delay_5min_9bp")),
        ),
        reverse=True,
    )
    payload = {
        "schema_version": "1.0.0", "status": "COMPLETE", "version_range": [FIRST_VERSION, LAST_VERSION],
        "hypotheses": len(records), "comparison_cells": total_cells,
        "strict_pre_factory_null_passes": sum(item["strict_pre_factory_null_pass"] for item in records),
        "elapsed_seconds": time.perf_counter() - started, "records": records,
    }
    v34.v12._atomic(args.output, payload)
    print(json.dumps({
        "status": payload["status"], "hypotheses": len(records),
        "strict_pre_factory_null_passes": payload["strict_pre_factory_null_passes"],
        "best": records[0]["candidate_id"], "elapsed_seconds": payload["elapsed_seconds"],
    }))


if __name__ == "__main__":
    main()
