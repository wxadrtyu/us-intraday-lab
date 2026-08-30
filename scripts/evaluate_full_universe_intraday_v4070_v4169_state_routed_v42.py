"""Preregistered causal state routing across frozen v42 parents."""

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
import evaluate_full_universe_intraday_v35_rank_ensemble as v35
import evaluate_full_universe_intraday_v39_multifactor_regime_gate as v39
import evaluate_full_universe_intraday_v42_multifactor_vol_target as v42
import evaluate_full_universe_intraday_v47_score_slope as v47
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 4070
LAST_VERSION = 4169
PRIOR_COMPARISON_CELLS = 201_905
SOURCE_SHA256 = "babfd6e0b9262ddc83ea0d046f00ad40fbe3d9ac313669a7c20b50301758c327"
QUANTILES = (0.20, 0.35, 0.50, 0.65, 0.80)
WEAK_EXPOSURES = (0.0, 0.25)
STATE_FAMILIES = {
    "broad_risk_on": {"spy_current": 1, "spy_prior20": 1, "sector_breadth": 1, "spy_volatility": -1},
    "growth_risk_on": {"qqq_current": 1, "tech_minus_market": 1, "sector_breadth": 1, "spy_volatility": -1},
    "oversold_rebound": {"spy_prior20": -1, "spy_current": 1, "sector_breadth": 1, "risk_asset_agreement": 1},
    "capitulation_repair": {"spy_current": -1, "spy_volatility": 1, "sector_breadth": -1, "risk_asset_agreement": -1},
    "low_dispersion_trend": {"spy_current": 1, "sector_dispersion": -1, "sector_breadth": 1, "risk_asset_agreement": 1},
    "cyclical_confirmation": {"cyclical_minus_defensive": 1, "spy_current": 1, "sector_breadth": 1, "spy_volatility": -1},
    "small_cap_confirmation": {"iwm_current": 1, "qqq_minus_iwm": -1, "sector_breadth": 1, "risk_asset_agreement": 1},
    "tech_leadership": {"qqq_current": 1, "tech_minus_market": 1, "cyclical_minus_defensive": 1, "sector_dispersion": -1},
    "high_vol_recovery": {"spy_volatility": 1, "spy_current": 1, "sector_breadth": 1, "risk_asset_agreement": 1},
    "balanced_confirmation": {"spy_prior20": 1, "spy_current": 1, "qqq_current": 1, "sector_breadth": 1, "risk_asset_agreement": 1, "spy_volatility": -1},
}


def specifications() -> list[tuple[str, float, float]]:
    return list(itertools.product(STATE_FAMILIES, QUANTILES, WEAK_EXPOSURES))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _identity(definition: dict) -> str:
    return hashlib.sha256(json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def _state_values(cube: cross.Cube, decision: int, names: tuple[str, ...]) -> np.ndarray:
    available = cube.factors(decision)
    return np.stack([available[name][:, 0] for name in names], axis=1)


def _state_model(cube: cross.Cube, decision: int, coefficients: dict[str, int], quantile: float):
    names = tuple(coefficients)
    matrix = _state_values(cube, decision, names)
    train = cube.masks()["train_2022_2023"]
    values = matrix[train & np.isfinite(matrix).all(axis=1)]
    mean, scale = values.mean(axis=0), values.std(axis=0)
    scale[scale < 1e-8] = 1.0
    direction = np.asarray([coefficients[name] for name in names])
    score = np.mean((matrix - mean) / scale * direction, axis=1)
    threshold = float(np.quantile(score[train & np.isfinite(score)], quantile))
    return {"names": names, "mean": mean, "scale": scale, "direction": direction, "threshold": threshold}


def _state_score(cube: cross.Cube, decision: int, model: dict) -> np.ndarray:
    matrix = _state_values(cube, decision, tuple(model["names"]))
    return np.mean((matrix - model["mean"]) / model["scale"] * model["direction"], axis=1)


def _parent_streams(cube: cross.Cube, parent: dict, model):
    raw = (
        v35._sleeve(cube, model, v34.STANDARD_COST, 0),
        v35._sleeve(cube, model, v34.STRESS_COST, 0),
        v35._sleeve(cube, model, v34.STANDARD_COST, 1),
    )
    definition = parent["definition"]
    exposure = v42._exposure(
        raw[0].values, int(definition["lookback"]),
        float(definition["target_volatility"]), float(definition["minimum_exposure"]),
    )
    return tuple(v42._scaled(stream, exposure) for stream in raw)


def _route(stream, score: np.ndarray, threshold: float, weak_exposure: float):
    exposure = np.where(np.isfinite(score) & (score >= threshold), 1.0, weak_exposure)
    return v42._scaled(stream, exposure)


def _observe(cube, stream):
    return v47._observe(cube, stream, True)


def _primary(observation: dict) -> bool:
    oos = observation["development_oos_2024_2025"]
    return (
        float(oos["annualized_return"]) >= 0.50 and float(oos["max_drawdown"]) < 0.20
        and float(oos["information_ratio"]) >= 1.0
        and all(float(observation[name]["annualized_return"]) > 0 for name in ("train_2022_2023", "2024", "2025"))
    )


def _rank(observations: tuple[dict, ...]) -> tuple[float, float, float]:
    return (
        min(float(item["development_oos_2024_2025"]["annualized_return"]) for item in observations),
        min(float(item["development_oos_2024_2025"]["information_ratio"]) for item in observations),
        min(float(observations[0][name]["annualized_return"]) for name in ("train_2022_2023", "2024", "2025")),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if _sha(args.source) != SOURCE_SHA256:
        raise RuntimeError("V42_SOURCE_HASH_CHANGED")
    started = time.perf_counter()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    parents = source["records"]
    if len(parents) != 500 or len(specifications()) != 100:
        raise RuntimeError("STATE_ROUTING_PREREGISTRATION_MISMATCH")
    development = cross.Cube(args.root, "alpaca", 0)
    historical = cross.Cube(args.root, "historical", 0)
    parent_models = {
        parent["candidate_id"]: v39._models(development, [parent["definition"]["strategy"]])[0]
        for parent in parents
    }
    dev_parent_streams = {
        parent["candidate_id"]: _parent_streams(development, parent, parent_models[parent["candidate_id"]])
        for parent in parents
    }
    hist_parent_streams = {
        parent["candidate_id"]: _parent_streams(historical, parent, parent_models[parent["candidate_id"]])
        for parent in parents
    }
    parent_decisions = {
        parent["candidate_id"]: int(parent["definition"]["strategy"]["decision"])
        for parent in parents
    }
    records = []
    evaluated_cells = 0
    total_cells = PRIOR_COMPARISON_CELLS + len(parents) * len(specifications())
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    for offset, (family, quantile, weak_exposure) in enumerate(specifications()):
        coefficients = STATE_FAMILIES[family]
        state_models = {
            decision: _state_model(development, decision, coefficients, quantile)
            for decision in set(parent_decisions.values())
        }
        dev_scores = {
            decision: _state_score(development, decision, model) for decision, model in state_models.items()
        }
        cells = []
        for parent in parents:
            candidate_id = parent["candidate_id"]
            decision = parent_decisions[candidate_id]
            streams = tuple(
                _route(stream, dev_scores[decision], state_models[decision]["threshold"], weak_exposure)
                for stream in dev_parent_streams[candidate_id]
            )
            observations = tuple(_observe(development, stream) for stream in streams)
            cells.append({"parent": parent, "streams": streams, "observations": observations, "rank": _rank(observations), "primary": all(_primary(item) for item in observations)})
        evaluated_cells += len(cells)
        cells.sort(key=lambda item: item["rank"], reverse=True)
        for cell in cells[:3]:
            parent = cell["parent"]
            candidate_id = parent["candidate_id"]
            decision = parent_decisions[candidate_id]
            model = state_models[decision]
            hist_score = _state_score(historical, decision, model)
            hist_streams = tuple(
                _route(stream, hist_score, model["threshold"], weak_exposure)
                for stream in hist_parent_streams[candidate_id]
            )
            historical_obs = tuple(_observe(historical, stream)["historical_2018_2020"] for stream in hist_streams)
            streams, observations = cell["streams"], cell["observations"]
            fold_metrics = {
                name: [metrics(stream.values[index], stream.benchmark[index], stream.active[index]) for index in folds]
                for name, stream in zip(("standard", "cost_18bp", "delay_5min_9bp"), streams, strict=True)
            }
            starts = {}
            for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
                mask = development.masks()["development_all"] & (development.dates >= pd.Timestamp(start))
                starts[start] = metrics(streams[0].values[mask], streams[0].benchmark[mask], streams[0].active[mask])
            siblings = [item for item in cells if item["parent"]["definition"]["strategy"] == parent["definition"]["strategy"]]
            neighborhood = sum(item["primary"] for item in siblings) / len(siblings)
            oos = observations[0]["development_oos_2024_2025"]
            z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
            bonferroni = min(1.0, 2.0 * v47._normal_tail(abs(z_score)) * total_cells)
            gates = {
                "standard_primary": _primary(observations[0]), "cost_18bp_primary": _primary(observations[1]),
                "delay_5min_primary": _primary(observations[2]),
                "four_of_five_positive_folds_all_scenarios": all(sum(float(x["annualized_return"]) > 0 for x in values) >= 4 for values in fold_metrics.values()),
                "all_start_dates_positive": all(float(x["annualized_return"]) > 0 for x in starts.values()),
                "historical_15pct_mdd_below_20pct_all_scenarios": all(float(x["annualized_return"]) >= 0.15 and float(x["max_drawdown"]) < 0.20 for x in historical_obs),
                "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
                "consumed_2026q1_above_5pct": float(observations[0]["consumed_2026q1"]["total_return"]) > 0.05,
                "consumed_2026_total_above_5pct": float(observations[0]["consumed_2026_all"]["total_return"]) > 0.05,
                "cumulative_bonferroni_5pct": bonferroni < 0.05,
            }
            definition = {
                "version": FIRST_VERSION + offset, "mechanism": "causal_state_routed_v42",
                "state_family": family, "state_quantile": quantile, "weak_exposure": weak_exposure,
                "parent_candidate_id": candidate_id, "parent_definition": parent["definition"],
            }
            records.append({
                "candidate_id": f"lev-v{FIRST_VERSION + offset}-" + _identity(definition),
                "definition": definition,
                "state_model": {"names": model["names"], "mean": model["mean"].tolist(), "scale": model["scale"].tolist(), "direction": model["direction"].tolist(), "threshold": model["threshold"]},
                "standard": observations[0], "cost_18bp": observations[1], "delay_5min_9bp": observations[2],
                "historical_scenarios": {"standard": historical_obs[0], "cost_18bp": historical_obs[1], "delay_5min_9bp": historical_obs[2]},
                "development_folds": fold_metrics, "start_date_stress": starts,
                "neighbor_primary_share": neighborhood,
                "multiple_comparison": {"total_cells": total_cells, "z_score": z_score, "bonferroni_p": bonferroni},
                "gates": gates, "strict_pre_factory_null_pass": all(gates.values()),
            })
        print(json.dumps({"progress": f"{offset + 1}/100", "version": FIRST_VERSION + offset, "best_rank": cells[0]["rank"]}), flush=True)
    records.sort(key=lambda item: _rank((item["standard"], item["cost_18bp"], item["delay_5min_9bp"])), reverse=True)
    payload = {
        "schema_version": "1.0.0", "status": "COMPLETE", "version_range": [FIRST_VERSION, LAST_VERSION],
        "versions": 100, "evaluated_cells": evaluated_cells, "comparison_cells": total_cells,
        "strict_pre_factory_null_passes": sum(item["strict_pre_factory_null_pass"] for item in records),
        "elapsed_seconds": time.perf_counter() - started, "records": records,
    }
    v34.v12._atomic(args.output, payload)
    print(json.dumps({"status": "COMPLETE", "evaluated_cells": evaluated_cells, "strict_pre_factory_null_passes": payload["strict_pre_factory_null_passes"], "best": records[0]["candidate_id"], "elapsed_seconds": payload["elapsed_seconds"]}))


if __name__ == "__main__":
    main()
