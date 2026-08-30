"""Preregistered second-state override of the historically robust v4210 route."""

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
import evaluate_full_universe_intraday_v4170_v4269_dual_parent_routing as dual
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

FIRST_VERSION = 4370
LAST_VERSION = 4469
PRIOR_COMPARISON_CELLS = 253_005
SOURCE_SHA256 = prior.SOURCE_SHA256
MODERN_PARENT = dual.MODERN_PARENT
TRANSFER_PARENT = "lev-v42t-b5dc591391ab516c"
QUANTILES = (0.20, 0.35, 0.50, 0.65, 0.80)
ORIENTATIONS = ("override_on_high", "override_on_low")
CORE_FAMILY = "low_dispersion_trend"
CORE_QUANTILE = 0.20
CORE_ORIENTATION = "modern_on_high"
STATE_FAMILIES = {
    "broad_crash": {"spy_current": -1, "qqq_current": -1, "iwm_current": -1, "sector_breadth": -1},
    "volatile_crash": {"spy_current": -1, "spy_volatility": 1, "sector_breadth": -1, "risk_asset_agreement": -1},
    "growth_crash": {"qqq_current": -1, "tech_minus_market": -1, "sector_breadth": -1, "spy_volatility": 1},
    "small_cap_crash": {"iwm_current": -1, "qqq_minus_iwm": 1, "sector_breadth": -1, "spy_volatility": 1},
    "dispersion_crash": {"sector_dispersion": 1, "spy_current": -1, "sector_breadth": -1, "risk_asset_agreement": -1},
    "oversold_repair": {"spy_current": -1, "sector_breadth": 1, "risk_asset_agreement": 1, "spy_volatility": 1},
    "growth_repair": {"qqq_current": -1, "tech_minus_market": 1, "sector_breadth": 1, "spy_volatility": 1},
    "small_cap_repair": {"iwm_current": -1, "qqq_minus_iwm": -1, "sector_breadth": 1, "risk_asset_agreement": 1},
    "cyclical_repair": {"cyclical_minus_defensive": 1, "spy_current": -1, "sector_breadth": 1, "spy_volatility": 1},
    "concentrated_repair": {"qqq_minus_iwm": 1, "tech_minus_market": 1, "spy_current": -1, "sector_dispersion": 1},
}


def specifications():
    return list(itertools.product(STATE_FAMILIES, QUANTILES, ORIENTATIONS))


def _identity(definition: dict) -> str:
    encoded = json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _override_mask(core_modern: np.ndarray, override_state: np.ndarray) -> np.ndarray:
    return (~core_modern) & override_state


def _primary(observation: dict) -> bool:
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
        min(float(observations[0][name]["annualized_return"]) for name in ("train_2022_2023", "2024", "2025")),
    )


def _routed_streams(parent_streams, core_modern, override_state):
    core = tuple(
        dual._choose(modern, transfer, core_modern)
        for modern, transfer in zip(parent_streams[MODERN_PARENT], parent_streams[TRANSFER_PARENT], strict=True)
    )
    use_override = _override_mask(core_modern, override_state)
    return tuple(
        dual._choose(modern, routed, use_override)
        for modern, routed in zip(parent_streams[MODERN_PARENT], core, strict=True)
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
    required = (MODERN_PARENT, TRANSFER_PARENT)
    if any(candidate_id not in parent_map for candidate_id in required) or len(specifications()) != 100:
        raise RuntimeError("CRASH_OVERRIDE_PREREGISTRATION_MISMATCH")

    development = v34.Cube(args.root, "alpaca", 0)
    historical = v34.Cube(args.root, "historical", 0)
    development_state = state.v53.Cube(args.root, "alpaca", 0)
    historical_state = state.v53.Cube(args.root, "historical", 0)
    if not np.array_equal(development.dates, development_state.dates) or not np.array_equal(historical.dates, historical_state.dates):
        raise RuntimeError("STATE_AND_PARENT_CUBES_MISALIGNED")

    models = {
        candidate_id: v39._models(development, [parent_map[candidate_id]["definition"]["strategy"]])[0]
        for candidate_id in required
    }
    dev_parents = {
        candidate_id: prior._parent_streams(development, parent_map[candidate_id], models[candidate_id])
        for candidate_id in required
    }
    hist_parents = {
        candidate_id: prior._parent_streams(historical, parent_map[candidate_id], models[candidate_id])
        for candidate_id in required
    }
    core_model = dual._fit_state(development_state, dual.STATE_FAMILIES[CORE_FAMILY], CORE_QUANTILE)
    dev_core_score = dual._score(development_state, core_model)
    dev_core_modern = np.isfinite(dev_core_score) & (dev_core_score >= core_model["threshold"])
    hist_core_score = dual._score(historical_state, core_model)
    hist_core_modern = np.isfinite(hist_core_score) & (hist_core_score >= core_model["threshold"])

    cells = []
    for offset, (family, quantile, orientation) in enumerate(specifications()):
        override_model = dual._fit_state(development_state, STATE_FAMILIES[family], quantile)
        score = dual._score(development_state, override_model)
        high = np.isfinite(score) & (score >= override_model["threshold"])
        override_state = high if orientation == "override_on_high" else ~high
        streams = _routed_streams(dev_parents, dev_core_modern, override_state)
        observations = tuple(v47._observe(development, stream, True) for stream in streams)
        cells.append({
            "version": FIRST_VERSION + offset,
            "family": family,
            "quantile": quantile,
            "orientation": orientation,
            "override_model": override_model,
            "streams": streams,
            "observations": observations,
            "rank": _rank(observations),
            "primary": all(_primary(item) for item in observations),
        })

    total_cells = PRIOR_COMPARISON_CELLS + len(cells)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    for cell in cells:
        model = cell["override_model"]
        score = dual._score(historical_state, model)
        high = np.isfinite(score) & (score >= model["threshold"])
        hist_override_state = high if cell["orientation"] == "override_on_high" else ~high
        historical_streams = _routed_streams(hist_parents, hist_core_modern, hist_override_state)
        historical_obs = tuple(v47._observe(historical, stream, True)["historical_2018_2020"] for stream in historical_streams)
        streams, observations = cell["streams"], cell["observations"]
        fold_metrics = {
            name: [metrics(stream.values[index], stream.benchmark[index], stream.active[index]) for index in folds]
            for name, stream in zip(("standard", "cost_18bp", "delay_5min_9bp"), streams, strict=True)
        }
        starts = {}
        for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
            mask = development.masks()["development_all"] & (development.dates >= pd.Timestamp(start))
            starts[start] = metrics(streams[0].values[mask], streams[0].benchmark[mask], streams[0].active[mask])
        q_index = QUANTILES.index(cell["quantile"])
        neighbors = [
            item for item in cells
            if item["family"] == cell["family"]
            and item["orientation"] == cell["orientation"]
            and abs(QUANTILES.index(item["quantile"]) - q_index) <= 1
        ]
        neighborhood = sum(item["primary"] for item in neighbors) / len(neighbors)
        oos = observations[0]["development_oos_2024_2025"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * v47._normal_tail(abs(z_score)) * total_cells)
        gates = {
            "standard_primary": _primary(observations[0]),
            "cost_18bp_primary": _primary(observations[1]),
            "delay_5min_primary": _primary(observations[2]),
            "four_of_five_positive_folds_all_scenarios": all(sum(float(item["annualized_return"]) > 0 for item in values) >= 4 for values in fold_metrics.values()),
            "all_start_dates_positive": all(float(item["annualized_return"]) > 0 for item in starts.values()),
            "historical_15pct_mdd_below_20pct_all_scenarios": all(float(item["annualized_return"]) >= 0.15 and float(item["max_drawdown"]) < 0.20 for item in historical_obs),
            "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
            "consumed_2026q1_above_5pct": float(observations[0]["consumed_2026q1"]["total_return"]) > 0.05,
            "consumed_2026_total_above_5pct": float(observations[0]["consumed_2026_all"]["total_return"]) > 0.05,
            "cumulative_bonferroni_5pct": bonferroni < 0.05,
        }
        definition = {
            "version": cell["version"],
            "mechanism": "v4210_prior_close_crash_override",
            "core_candidate": "lev-v4210-c1aa5b2dbe4d79d4",
            "override_parent": MODERN_PARENT,
            "override_state_family": cell["family"],
            "override_state_quantile": cell["quantile"],
            "override_orientation": cell["orientation"],
        }
        records.append({
            "candidate_id": f"lev-v{cell['version']}-" + _identity(definition),
            "definition": definition,
            "override_state_model": {
                "names": model["names"], "mean": model["mean"].tolist(), "scale": model["scale"].tolist(),
                "direction": model["direction"].tolist(), "threshold": model["threshold"],
            },
            "standard": observations[0], "cost_18bp": observations[1], "delay_5min_9bp": observations[2],
            "historical_scenarios": {"standard": historical_obs[0], "cost_18bp": historical_obs[1], "delay_5min_9bp": historical_obs[2]},
            "development_folds": fold_metrics, "start_date_stress": starts, "neighbor_primary_share": neighborhood,
            "multiple_comparison": {"total_cells": total_cells, "z_score": z_score, "bonferroni_p": bonferroni},
            "gates": gates, "strict_pre_factory_null_pass": all(gates.values()),
        })

    records.sort(key=lambda item: _rank((item["standard"], item["cost_18bp"], item["delay_5min_9bp"])), reverse=True)
    payload = {
        "schema_version": "1.0.0", "status": "COMPLETE", "version_range": [FIRST_VERSION, LAST_VERSION],
        "evaluated_cells": len(cells), "comparison_cells": total_cells,
        "strict_pre_factory_null_passes": sum(item["strict_pre_factory_null_pass"] for item in records),
        "elapsed_seconds": time.perf_counter() - started, "records": records,
    }
    v34.v12._atomic(args.output, payload)
    print(json.dumps({
        "status": "COMPLETE", "evaluated_cells": len(cells),
        "strict_pre_factory_null_passes": payload["strict_pre_factory_null_passes"],
        "best": records[0]["candidate_id"], "elapsed_seconds": payload["elapsed_seconds"],
    }))


if __name__ == "__main__":
    main()
