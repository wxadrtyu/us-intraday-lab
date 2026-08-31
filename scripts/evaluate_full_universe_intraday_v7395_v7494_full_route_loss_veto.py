"""v7395-v7494 causal loss-state veto over the frozen v6776 route."""

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
import evaluate_full_universe_intraday_v5670_v5769_modern_quality_gate as quality
import evaluate_full_universe_intraday_v5970_v6069_sector_flow_leadership as sector
import evaluate_full_universe_intraday_v6695_v6794_state_gated_wide_fill as base
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics
from us_intraday_lab.prospective_admission_policy import (
    EFFECTIVE_FIRST_VERSION,
    passes_global_evidence,
    passes_primary,
)

FIRST_VERSION = 7395
LAST_VERSION = 7494
PRIOR_COMPARISON_CELLS = 256_255
GATE_DECISION = 17
ENTRY_BAR = 24
QUANTILES = (0.0, 0.2, 0.4, 0.6, 0.8)
ALPHAS = (1.0, 100.0)
FACTOR_SETS = {
    "adverse_path": ("current_return", "relative_return", "drawdown_from_high", "return_acceleration", "close_location"),
    "adverse_flow": ("signed_volume_imbalance", "volume_acceleration", "recent_volume_ratio", "sector_signed_flow_breadth", "sector_return_flow_agreement"),
    "unstable_reclaim": ("rebound_from_low", "intraday_range_position", "recent_volatility_ratio", "sector_volatility_contraction", "sector_breadth_acceleration"),
    "growth_risk": ("relative_return", "vwap_distance", "growth_minus_defensive_return", "growth_minus_defensive_flow", "sector_flow_dispersion"),
    "leadership_fragility": ("current_rank", "path_efficiency", "sector_leadership_spread", "sector_leadership_concentration", "sector_path_efficiency_breadth"),
    "prior_state_path": ("prior1_return", "prior20_return", "spy_prior20", "drawdown_from_high", "return_acceleration"),
    "volatility_liquidity": ("realized_volatility", "recent_volatility_ratio", "recent_volume_ratio", "sector_volatility_contraction", "sector_flow_dispersion"),
    "breadth_repair": ("rebound_from_low", "return_acceleration", "sector_signed_flow_breadth", "sector_breadth_acceleration", "sector_return_flow_agreement"),
    "relative_absorption": ("relative_return", "signed_volume_imbalance", "close_location", "growth_minus_defensive_flow", "sector_path_efficiency_breadth"),
    "balanced_loss_veto": ("current_return", "relative_return", "drawdown_from_high", "rebound_from_low", "return_acceleration", "signed_volume_imbalance", "recent_volatility_ratio", "sector_signed_flow_breadth", "sector_breadth_acceleration", "growth_minus_defensive_flow"),
}


def specifications():
    return [(family, quantile, alpha) for family in FACTOR_SETS for quantile in QUANTILES for alpha in ALPHAS]


def _identity(definition: dict) -> str:
    payload = json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def _veto(stream, allowed):
    active = stream.active & allowed
    return v34.v12.ReturnStream(
        np.where(active, stream.values, 0.0),
        np.where(active, stream.benchmark, 0.0),
        active,
        np.where(active, stream.component_trades, 0),
    )


def _route(cube, cube_state, parents, core_model, override_model, gate_model, fill_model):
    base_ids = tuple(dict.fromkeys((base.prior.route.MODERN_PARENT, base.prior.route.TRANSFER_PARENT, base.prior.cash.FALLBACK_PARENT)))
    base_streams = base.prior._base_streams(cube, cube_state, {item: parents[item] for item in base_ids}, core_model, override_model, gate_model)
    fill = tuple(base.prior.wide.campaign._combine([parents[item][scenario] for item in base.FILL_PARENTS], base.FILL_WEIGHTS) for scenario in range(3))
    allowed = base._allowed(cube_state, fill_model, "fill_on_low")
    return tuple(base._disjoint_gated(anchor, extra, allowed) for anchor, extra in zip(base_streams, fill, strict=True))


def _primary(observation):
    if FIRST_VERSION >= EFFECTIVE_FIRST_VERSION:
        return passes_primary(observation)
    oos = observation["development_oos_2024_2025"]
    return float(oos["annualized_return"]) >= 0.50 and float(oos["max_drawdown"]) < 0.20 and float(oos["information_ratio"]) >= 1.0 and all(float(observation[name]["annualized_return"]) > 0 for name in ("train_2022_2023", "2024", "2025"))


def _rank(observations):
    return (min(float(item["development_oos_2024_2025"]["information_ratio"]) for item in observations), min(float(item["development_oos_2024_2025"]["annualized_return"]) for item in observations))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if base.prior.parent._sha(args.source) != base.prior.SOURCE_SHA256:
        raise RuntimeError("V42_SOURCE_HASH_CHANGED")
    if len(specifications()) != 100 or GATE_DECISION >= ENTRY_BAR:
        raise RuntimeError("FULL_ROUTE_VETO_PREREGISTRATION_MISMATCH")
    started = time.perf_counter()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    source_map = {item["candidate_id"]: item for item in source["records"]}
    base.prior.cash._configure()
    base_ids = tuple(dict.fromkeys((base.prior.route.MODERN_PARENT, base.prior.route.TRANSFER_PARENT, base.prior.cash.FALLBACK_PARENT)))
    required = tuple(dict.fromkeys((*base_ids, *base.FILL_PARENTS)))
    development = v34.Cube(args.root, "alpaca", 0)
    historical = v34.Cube(args.root, "historical", 0)
    development_factors = sector.SectorFlowLeadershipCube(args.root, "alpaca", 0)
    historical_factors = sector.SectorFlowLeadershipCube(args.root, "historical", 0)
    if not np.array_equal(development.dates, development_factors.dates) or not np.array_equal(
        historical.dates, historical_factors.dates
    ):
        raise RuntimeError("FACTOR_ROUTE_DATE_AXIS_MISMATCH")
    dev_state = base.prior.parent.cross.Cube(args.root, "alpaca", 0)
    hist_state = base.prior.parent.cross.Cube(args.root, "historical", 0)
    models = {item: v39._models(development, [source_map[item]["definition"]["strategy"]])[0] for item in required}
    dev_parents = {item: base.prior.parent._parent_streams(development, source_map[item], models[item]) for item in required}
    hist_parents = {item: base.prior.parent._parent_streams(historical, source_map[item], models[item]) for item in required}
    core_model = base.state._fit_state(dev_state, base.CORE_LOW_DISPERSION_TREND, 0.20)
    override_model = base.state._fit_state(dev_state, base.CORE_OVERSOLD_REPAIR, 0.35)
    _, transfer_state = base.prior.route._base_state(dev_state, core_model, override_model)
    gate_model = base.prior.route._fit_gate(development, dev_parents[base.prior.route.TRANSFER_PARENT][0], transfer_state, base.prior.route.FACTOR_SETS[base.prior.BASE_FAMILY], base.prior.BASE_QUANTILE, base.prior.BASE_ALPHA)
    fill_model = base.state._fit_state(dev_state, base.state.STATE_FAMILIES["high_vol_recovery"], 0.20)
    dev_route = _route(development, dev_state, dev_parents, core_model, override_model, gate_model, fill_model)
    hist_route = _route(historical, hist_state, hist_parents, core_model, override_model, gate_model, fill_model)
    cells = []
    for offset, (family, quantile, alpha) in enumerate(specifications()):
        model = quality._fit(development_factors, dev_route[0], dev_route[0].active, FACTOR_SETS[family], quantile, alpha)
        score = quality._score(development_factors, model)
        allowed = np.isfinite(score) & (score >= model["threshold"])
        streams = tuple(_veto(stream, allowed) for stream in dev_route)
        observations = tuple(v47._observe(development, stream, True) for stream in streams)
        cells.append({"version": FIRST_VERSION + offset, "family": family, "quantile": quantile, "alpha": alpha, "model": model, "streams": streams, "observations": observations, "primary": all(_primary(item) for item in observations)})
    total_cells = PRIOR_COMPARISON_CELLS + len(cells)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    for cell in cells:
        hist_score = quality._score(historical_factors, cell["model"])
        hist_allowed = np.isfinite(hist_score) & (hist_score >= cell["model"]["threshold"])
        hist_streams = tuple(_veto(stream, hist_allowed) for stream in hist_route)
        hist_obs = tuple(v47._observe(historical, stream, True)["historical_2018_2020"] for stream in hist_streams)
        streams, observations = cell["streams"], cell["observations"]
        fold_metrics = {name: [metrics(stream.values[index], stream.benchmark[index], stream.active[index]) for index in folds] for name, stream in zip(("standard", "cost_18bp", "delay_5min_9bp"), streams, strict=True)}
        starts = {}
        for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
            mask = development.masks()["development_all"] & (development.dates >= pd.Timestamp(start))
            starts[start] = metrics(streams[0].values[mask], streams[0].benchmark[mask], streams[0].active[mask])
        q_index, a_index = QUANTILES.index(cell["quantile"]), ALPHAS.index(cell["alpha"])
        neighbors = [item for item in cells if item["family"] == cell["family"] and abs(QUANTILES.index(item["quantile"]) - q_index) + abs(ALPHAS.index(item["alpha"]) - a_index) <= 1]
        neighborhood = sum(item["primary"] for item in neighbors) / len(neighbors)
        oos = observations[0]["development_oos_2024_2025"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        bonferroni = min(1.0, 2.0 * v47._normal_tail(abs(z_score)) * total_cells)
        global_gate_name = (
            "prospective_z_score_at_least_3"
            if FIRST_VERSION >= EFFECTIVE_FIRST_VERSION
            else "cumulative_bonferroni_5pct"
        )
        gates = {
            "standard_primary": _primary(observations[0]), "cost_18bp_primary": _primary(observations[1]), "delay_5min_primary": _primary(observations[2]),
            "four_of_five_positive_folds_all_scenarios": all(sum(float(item["annualized_return"]) > 0 for item in values) >= 4 for values in fold_metrics.values()),
            "all_start_dates_positive": all(float(item["annualized_return"]) > 0 for item in starts.values()),
            "historical_15pct_mdd_below_20pct_all_scenarios": all(float(item["annualized_return"]) >= 0.15 and float(item["max_drawdown"]) < 0.20 for item in hist_obs),
            "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
            "consumed_2026q1_above_5pct": float(observations[0]["consumed_2026q1"]["total_return"]) > 0.05,
            "consumed_2026_total_above_5pct": float(observations[0]["consumed_2026_all"]["total_return"]) > 0.05,
            global_gate_name: (
                passes_global_evidence(z_score)
                if FIRST_VERSION >= EFFECTIVE_FIRST_VERSION
                else bonferroni < 0.05
            ),
        }
        definition = {"version": cell["version"], "mechanism": "v6776_full_route_causal_loss_veto", "base_candidate": "lev-v6776-f28d61d0cb13f09d", "factor_set": cell["family"], "score_quantile": cell["quantile"], "ridge_alpha": cell["alpha"]}
        model = cell["model"]
        records.append({"candidate_id": f"lev-v{cell['version']}-" + _identity(definition), "definition": definition, "veto_model": {"factors": model["factors"], "mean": model["mean"].tolist(), "scale": model["scale"].tolist(), "coefficients": model["coefficients"].tolist(), "threshold": model["threshold"]}, "standard": observations[0], "cost_18bp": observations[1], "delay_5min_9bp": observations[2], "historical_scenarios": {"standard": hist_obs[0], "cost_18bp": hist_obs[1], "delay_5min_9bp": hist_obs[2]}, "development_folds": fold_metrics, "start_date_stress": starts, "neighbor_primary_share": neighborhood, "multiple_comparison": {"total_cells": total_cells, "z_score": z_score, "bonferroni_p": bonferroni}, "gates": gates, "strict_pre_factory_null_pass": all(gates.values())})
    records.sort(key=lambda item: _rank((item["standard"], item["cost_18bp"], item["delay_5min_9bp"])), reverse=True)
    payload = {"schema_version": "1.0.0", "status": "COMPLETE", "version_range": [FIRST_VERSION, LAST_VERSION], "evaluated_cells": len(cells), "comparison_cells": total_cells, "strict_pre_factory_null_passes": sum(item["strict_pre_factory_null_pass"] for item in records), "elapsed_seconds": time.perf_counter() - started, "records": records}
    v34.v12._atomic(args.output, payload)
    print(json.dumps({"status": "COMPLETE", "evaluated_cells": len(cells), "strict_pre_factory_null_passes": payload["strict_pre_factory_null_passes"], "best": records[0]["candidate_id"], "elapsed_seconds": payload["elapsed_seconds"]}))


if __name__ == "__main__":
    main()
