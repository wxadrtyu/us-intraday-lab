"""Preregistered prior-close routing between modern and transfer v42 parents."""

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
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 4170
LAST_VERSION = 4269
PRIOR_COMPARISON_CELLS = 251_905
SOURCE_SHA256 = prior.SOURCE_SHA256
MODERN_PARENT = "lev-v42t-6cc68a5a8184492a"
TRANSFER_PARENTS = (
    "lev-v42t-cc4126495da750c9", "lev-v42t-3e8239074db9b90e",
    "lev-v42t-b5dc591391ab516c", "lev-v42t-0b71a76bae6a1ee2",
    "lev-v42t-eea7306d4480eb6e", "lev-v42t-ec3c7192303d323f",
    "lev-v42t-5d9408f308823b54", "lev-v42t-2314f884f64b35f1",
    "lev-v42t-484653152afa12d6", "lev-v42t-a9a58647da4c6a9a",
)
QUANTILES = (0.20, 0.35, 0.50, 0.65, 0.80)
ORIENTATIONS = ("modern_on_high", "modern_on_low")
STATE_FAMILIES = {
    "broad_risk": {"spy_current": 1, "sector_breadth": 1, "risk_asset_agreement": 1, "spy_volatility": -1},
    "growth_leadership": {"qqq_current": 1, "tech_minus_market": 1, "sector_breadth": 1, "spy_volatility": -1},
    "oversold_repair": {"spy_current": -1, "sector_breadth": 1, "risk_asset_agreement": 1, "spy_volatility": 1},
    "dispersion_breakout": {"sector_dispersion": 1, "spy_current": 1, "qqq_current": 1, "risk_asset_agreement": 1},
    "low_dispersion_trend": {"sector_dispersion": -1, "spy_current": 1, "sector_breadth": 1, "risk_asset_agreement": 1},
    "cyclical_confirmation": {"cyclical_minus_defensive": 1, "spy_current": 1, "sector_breadth": 1, "spy_volatility": -1},
    "small_cap_confirmation": {"iwm_current": 1, "qqq_minus_iwm": -1, "sector_breadth": 1, "risk_asset_agreement": 1},
    "tech_concentration": {"qqq_minus_iwm": 1, "tech_minus_market": 1, "qqq_current": 1, "sector_dispersion": 1},
    "high_vol_recovery": {"spy_volatility": 1, "spy_current": 1, "sector_breadth": 1, "risk_asset_agreement": 1},
    "balanced_state": {"spy_current": 1, "qqq_current": 1, "iwm_current": 1, "sector_breadth": 1, "risk_asset_agreement": 1, "spy_volatility": -1},
}


def specifications():
    return list(itertools.product(STATE_FAMILIES, QUANTILES, ORIENTATIONS))


def _identity(definition: dict) -> str:
    return hashlib.sha256(json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def _fit_state(cube, coefficients: dict[str, int], quantile: float):
    matrix = state._state_matrix(cube, "prior_close")
    names = tuple(coefficients)
    values = np.stack([matrix[name] for name in names], axis=1)
    train = cube.masks()["train_2022_2023"]
    selected = values[train & np.isfinite(values).all(axis=1)]
    mean, scale = selected.mean(axis=0), selected.std(axis=0)
    scale[scale < 1e-8] = 1.0
    direction = np.asarray([coefficients[name] for name in names])
    score = np.mean((values - mean) / scale * direction, axis=1)
    threshold = float(np.quantile(score[train & np.isfinite(score)], quantile))
    return {"names": names, "mean": mean, "scale": scale, "direction": direction, "threshold": threshold}


def _score(cube, model):
    matrix = state._state_matrix(cube, "prior_close")
    values = np.stack([matrix[name] for name in model["names"]], axis=1)
    return np.mean((values - model["mean"]) / model["scale"] * model["direction"], axis=1)


def _choose(modern, transfer, choose_modern: np.ndarray):
    active = np.where(choose_modern, modern.active, transfer.active)
    return v34.v12.ReturnStream(
        np.where(choose_modern, modern.values, transfer.values),
        np.where(choose_modern, modern.benchmark, transfer.benchmark),
        active,
        np.where(choose_modern, modern.component_trades, transfer.component_trades),
    )


def _primary(observation: dict) -> bool:
    oos = observation["development_oos_2024_2025"]
    return (
        float(oos["annualized_return"]) >= 0.50 and float(oos["max_drawdown"]) < 0.20
        and float(oos["information_ratio"]) >= 1.0
        and all(float(observation[name]["annualized_return"]) > 0 for name in ("train_2022_2023", "2024", "2025"))
    )


def _rank(observations):
    return (
        min(float(x["development_oos_2024_2025"]["annualized_return"]) for x in observations),
        min(float(x["development_oos_2024_2025"]["information_ratio"]) for x in observations),
        min(float(observations[0][name]["annualized_return"]) for name in ("train_2022_2023", "2024", "2025")),
    )


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
    required = (MODERN_PARENT, *TRANSFER_PARENTS)
    if any(candidate_id not in parent_map for candidate_id in required) or len(specifications()) != 100:
        raise RuntimeError("DUAL_PARENT_PREREGISTRATION_MISMATCH")
    development = v34.Cube(args.root, "alpaca", 0)
    historical = v34.Cube(args.root, "historical", 0)
    development_state = state.v53.Cube(args.root, "alpaca", 0)
    historical_state = state.v53.Cube(args.root, "historical", 0)
    if not np.array_equal(development.dates, development_state.dates) or not np.array_equal(
        historical.dates, historical_state.dates
    ):
        raise RuntimeError("STATE_AND_PARENT_CUBES_MISALIGNED")
    models = {candidate_id: v39._models(development, [parent_map[candidate_id]["definition"]["strategy"]])[0] for candidate_id in required}
    dev_streams = {candidate_id: prior._parent_streams(development, parent_map[candidate_id], models[candidate_id]) for candidate_id in required}
    hist_streams = {candidate_id: prior._parent_streams(historical, parent_map[candidate_id], models[candidate_id]) for candidate_id in required}
    all_cells = []
    for offset, (family, quantile, orientation) in enumerate(specifications()):
        state_model = _fit_state(development_state, STATE_FAMILIES[family], quantile)
        score = _score(development_state, state_model)
        high = np.isfinite(score) & (score >= state_model["threshold"])
        choose_modern = high if orientation == "modern_on_high" else ~high
        for transfer_id in TRANSFER_PARENTS:
            streams = tuple(_choose(modern, transfer, choose_modern) for modern, transfer in zip(dev_streams[MODERN_PARENT], dev_streams[transfer_id], strict=True))
            observations = tuple(v47._observe(development, stream, True) for stream in streams)
            all_cells.append({
                "version": FIRST_VERSION + offset, "family": family, "quantile": quantile,
                "orientation": orientation, "transfer_id": transfer_id, "state_model": state_model,
                "streams": streams, "observations": observations, "rank": _rank(observations),
                "primary": all(_primary(item) for item in observations),
            })
    total_cells = PRIOR_COMPARISON_CELLS + len(all_cells)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    for version in range(FIRST_VERSION, LAST_VERSION + 1):
        frontier = sorted((cell for cell in all_cells if cell["version"] == version), key=lambda x: x["rank"], reverse=True)[:3]
        for cell in frontier:
            model = cell["state_model"]
            score = _score(historical_state, model)
            high = np.isfinite(score) & (score >= model["threshold"])
            choose_modern = high if cell["orientation"] == "modern_on_high" else ~high
            historical_routed = tuple(_choose(modern, transfer, choose_modern) for modern, transfer in zip(hist_streams[MODERN_PARENT], hist_streams[cell["transfer_id"]], strict=True))
            historical_obs = tuple(v47._observe(historical, stream, True)["historical_2018_2020"] for stream in historical_routed)
            streams, observations = cell["streams"], cell["observations"]
            fold_metrics = {name: [metrics(stream.values[index], stream.benchmark[index], stream.active[index]) for index in folds] for name, stream in zip(("standard", "cost_18bp", "delay_5min_9bp"), streams, strict=True)}
            starts = {}
            for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
                mask = development.masks()["development_all"] & (development.dates >= pd.Timestamp(start))
                starts[start] = metrics(streams[0].values[mask], streams[0].benchmark[mask], streams[0].active[mask])
            q_index = QUANTILES.index(cell["quantile"])
            neighbors = [x for x in all_cells if x["family"] == cell["family"] and x["orientation"] == cell["orientation"] and x["transfer_id"] == cell["transfer_id"] and abs(QUANTILES.index(x["quantile"]) - q_index) <= 1]
            neighborhood = sum(x["primary"] for x in neighbors) / len(neighbors)
            oos = observations[0]["development_oos_2024_2025"]
            z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
            bonferroni = min(1.0, 2.0 * v47._normal_tail(abs(z_score)) * total_cells)
            gates = {
                "standard_primary": _primary(observations[0]), "cost_18bp_primary": _primary(observations[1]), "delay_5min_primary": _primary(observations[2]),
                "four_of_five_positive_folds_all_scenarios": all(sum(float(x["annualized_return"]) > 0 for x in values) >= 4 for values in fold_metrics.values()),
                "all_start_dates_positive": all(float(x["annualized_return"]) > 0 for x in starts.values()),
                "historical_15pct_mdd_below_20pct_all_scenarios": all(float(x["annualized_return"]) >= 0.15 and float(x["max_drawdown"]) < 0.20 for x in historical_obs),
                "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
                "consumed_2026q1_above_5pct": float(observations[0]["consumed_2026q1"]["total_return"]) > 0.05,
                "consumed_2026_total_above_5pct": float(observations[0]["consumed_2026_all"]["total_return"]) > 0.05,
                "cumulative_bonferroni_5pct": bonferroni < 0.05,
            }
            definition = {"version": version, "mechanism": "prior_close_dual_parent_routing", "state_family": cell["family"], "state_quantile": cell["quantile"], "orientation": cell["orientation"], "modern_parent": MODERN_PARENT, "transfer_parent": cell["transfer_id"]}
            records.append({
                "candidate_id": f"lev-v{version}-" + _identity(definition), "definition": definition,
                "state_model": {"names": model["names"], "mean": model["mean"].tolist(), "scale": model["scale"].tolist(), "direction": model["direction"].tolist(), "threshold": model["threshold"]},
                "standard": observations[0], "cost_18bp": observations[1], "delay_5min_9bp": observations[2],
                "historical_scenarios": {"standard": historical_obs[0], "cost_18bp": historical_obs[1], "delay_5min_9bp": historical_obs[2]},
                "development_folds": fold_metrics, "start_date_stress": starts, "neighbor_primary_share": neighborhood,
                "multiple_comparison": {"total_cells": total_cells, "z_score": z_score, "bonferroni_p": bonferroni},
                "gates": gates, "strict_pre_factory_null_pass": all(gates.values()),
            })
    records.sort(key=lambda x: _rank((x["standard"], x["cost_18bp"], x["delay_5min_9bp"])), reverse=True)
    payload = {"schema_version": "1.0.0", "status": "COMPLETE", "version_range": [FIRST_VERSION, LAST_VERSION], "evaluated_cells": len(all_cells), "comparison_cells": total_cells, "strict_pre_factory_null_passes": sum(x["strict_pre_factory_null_pass"] for x in records), "elapsed_seconds": time.perf_counter() - started, "records": records}
    v34.v12._atomic(args.output, payload)
    print(json.dumps({"status": "COMPLETE", "evaluated_cells": len(all_cells), "strict_pre_factory_null_passes": payload["strict_pre_factory_null_passes"], "best": records[0]["candidate_id"], "elapsed_seconds": payload["elapsed_seconds"]}))


if __name__ == "__main__":
    main()
