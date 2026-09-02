"""Causal portfolio-volatility overlays for the frozen v11098 route."""

from __future__ import annotations

import argparse
import itertools
import json
import math
import time
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v39_multifactor_regime_gate as v39
import evaluate_full_universe_intraday_v47_score_slope as v47
import evaluate_full_universe_intraday_v5970_v6069_sector_flow_leadership as sector
import evaluate_full_universe_intraday_v11006_v11105_branch_causal as branch
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics
from us_intraday_lab.prospective_admission_policy import passes_global_evidence, passes_primary

FIRST_VERSION = 11307
LAST_VERSION = 11406
PRIOR_COMPARISON_CELLS = 298_783
LOOKBACKS = (10, 15, 20, 30, 40)
TARGETS = (0.20, 0.30, 0.40, 0.50, 0.60)
FLOORS = (0.25, 0.50, 0.75, 0.90)
BASE_CANDIDATE = "lev-v11098-2ddc1d07c9cfe31e"
LOW_EXPOSURE = 0.25


def specifications() -> list[tuple[int, float, float]]:
    return list(itertools.product(LOOKBACKS, TARGETS, FLOORS))


def _combine(opening, route, exposure):
    return v34.v12.ReturnStream(
        opening.values + route.values * exposure,
        opening.benchmark + route.benchmark * exposure,
        opening.active | route.active,
        opening.component_trades + route.component_trades,
    )


def _base_streams(root: Path, source_path: Path, selection_path: Path, *, return_components=False):
    branch._configure()
    campaign = branch.boundary.logical.clock.parent.parent.sparse_veto.campaign
    if campaign.base.prior.parent._sha(source_path) != campaign.base.prior.SOURCE_SHA256:
        raise RuntimeError("V11307_SOURCE_HASH_CHANGED")
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source_map = {item["candidate_id"]: item for item in source["records"]}
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    chosen = next(item for item in selection["records"] if item["candidate_id"] == BASE_CANDIDATE)
    definition = chosen["definition"]
    campaign.base.prior.cash._configure()
    base_ids = tuple(
        dict.fromkeys(
            (
                campaign.base.prior.route.MODERN_PARENT,
                campaign.base.prior.route.TRANSFER_PARENT,
                campaign.base.prior.cash.FALLBACK_PARENT,
            )
        )
    )
    required = tuple(dict.fromkeys((*base_ids, *campaign.base.FILL_PARENTS)))
    development = v34.Cube(root, "alpaca", 0)
    historical = v34.Cube(root, "historical", 0)
    dev_factors = sector.SectorFlowLeadershipCube(root, "alpaca", 0)
    hist_factors = sector.SectorFlowLeadershipCube(root, "historical", 0)
    dev_state = campaign.base.prior.parent.cross.Cube(root, "alpaca", 0)
    hist_state = campaign.base.prior.parent.cross.Cube(root, "historical", 0)
    models = {
        item: v39._models(development, [source_map[item]["definition"]["strategy"]])[0]
        for item in required
    }
    dev_parents = {
        item: campaign.base.prior.parent._parent_streams(
            development, source_map[item], models[item]
        )
        for item in required
    }
    hist_parents = {
        item: campaign.base.prior.parent._parent_streams(historical, source_map[item], models[item])
        for item in required
    }
    core_model = campaign.base.state._fit_state(
        dev_state, campaign.base.CORE_LOW_DISPERSION_TREND, 0.20
    )
    override_model = campaign.base.state._fit_state(
        dev_state, campaign.base.CORE_OVERSOLD_REPAIR, 0.35
    )
    _, transfer_state = campaign.base.prior.route._base_state(dev_state, core_model, override_model)
    gate_model = campaign.base.prior.route._fit_gate(
        development,
        dev_parents[campaign.base.prior.route.TRANSFER_PARENT][0],
        transfer_state,
        campaign.base.prior.route.FACTOR_SETS[campaign.base.prior.BASE_FAMILY],
        campaign.base.prior.BASE_QUANTILE,
        campaign.base.prior.BASE_ALPHA,
    )
    fill_model = campaign.base.state._fit_state(
        dev_state, campaign.base.state.STATE_FAMILIES["high_vol_recovery"], 0.20
    )
    dev_routes = campaign._route(
        development,
        dev_state,
        dev_parents,
        core_model,
        override_model,
        gate_model,
        fill_model,
    )
    hist_routes = campaign._route(
        historical,
        hist_state,
        hist_parents,
        core_model,
        override_model,
        gate_model,
        fill_model,
    )
    opening_parent = branch.boundary.logical.clock.parent.parent
    dev_openings = tuple(opening_parent._opening_by_late_stream[id(route)] for route in dev_routes)
    hist_openings = tuple(
        opening_parent._opening_by_late_stream[id(route)] for route in hist_routes
    )
    outer_model = campaign.quality._fit(
        dev_factors,
        dev_routes[0],
        dev_routes[0].active,
        campaign.FACTOR_SETS[definition["factor_set"]],
        float(definition["score_quantile"]),
        float(definition["ridge_alpha"]),
    )
    dev_score = campaign.quality._score(dev_factors, outer_model)
    hist_score = campaign.quality._score(hist_factors, outer_model)
    dev_outer = np.where(
        np.isfinite(dev_score) & (dev_score >= outer_model["threshold"]),
        1.0,
        LOW_EXPOSURE,
    )
    hist_outer = np.where(
        np.isfinite(hist_score) & (hist_score >= outer_model["threshold"]),
        1.0,
        LOW_EXPOSURE,
    )
    dev_streams = tuple(
        _combine(opening, route, dev_outer)
        for opening, route in zip(dev_openings, dev_routes, strict=True)
    )
    hist_streams = tuple(
        _combine(opening, route, hist_outer)
        for opening, route in zip(hist_openings, hist_routes, strict=True)
    )
    if return_components:
        return (
            development,
            historical,
            dev_openings,
            dev_routes,
            dev_outer,
            hist_openings,
            hist_routes,
            hist_outer,
        )
    return development, historical, dev_streams, hist_streams


def _portfolio_exposure(values, lookback: int, target: float, floor: float):
    values = np.asarray(values)
    exposure = np.ones(len(values))
    for index in range(lookback, len(values)):
        realized = float(np.std(values[index - lookback : index], ddof=1) * np.sqrt(252.0))
        if np.isfinite(realized) and realized > 1e-8:
            exposure[index] = np.clip(target / realized, floor, 1.0)
    return exposure


def _scale(streams, lookback: int, target: float, floor: float):
    exposure = _portfolio_exposure(streams[0].values, lookback, target, floor)
    return tuple(
        v34.v12.ReturnStream(
            stream.values * exposure,
            stream.benchmark * exposure,
            stream.active,
            stream.component_trades,
        )
        for stream in streams
    )


def _observe(cube, streams):
    return tuple(v47._observe(cube, stream, True) for stream in streams)


def _neighbor_share(cells, selected) -> float:
    chosen = selected["parameters"]
    axes = (LOOKBACKS, TARGETS, FLOORS)
    chosen_indexes = tuple(
        axis.index(chosen[name])
        for axis, name in zip(axes, ("lookback", "target", "floor"), strict=True)
    )
    neighbors = []
    for cell in cells:
        parameters = cell["parameters"]
        indexes = tuple(
            axis.index(parameters[name])
            for axis, name in zip(axes, ("lookback", "target", "floor"), strict=True)
        )
        if sum(abs(left - right) for left, right in zip(chosen_indexes, indexes, strict=True)) <= 1:
            neighbors.append(cell)
    return sum(item["primary"] for item in neighbors) / len(neighbors)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(specifications()) != 100:
        raise RuntimeError("V11307_PREREGISTRATION_MISMATCH")
    started = time.perf_counter()
    development, historical, base_dev, base_hist = _base_streams(
        args.root, args.source, args.selection
    )
    cells = []
    for version, (lookback, target, floor) in enumerate(specifications(), start=FIRST_VERSION):
        dev_streams = _scale(base_dev, lookback, target, floor)
        hist_streams = _scale(base_hist, lookback, target, floor)
        observations = _observe(development, dev_streams)
        hist_observations = tuple(
            v47._observe(historical, stream, True)["historical_2018_2020"]
            for stream in hist_streams
        )
        cells.append(
            {
                "version": version,
                "parameters": {"lookback": lookback, "target": target, "floor": floor},
                "streams": dev_streams,
                "observations": observations,
                "historical": hist_observations,
                "primary": all(passes_primary(item) for item in observations),
            }
        )
    total_cells = PRIOR_COMPARISON_CELLS + len(cells)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    for cell in cells:
        observations = cell["observations"]
        fold_metrics = {
            name: [
                metrics(stream.values[index], stream.benchmark[index], stream.active[index])
                for index in folds
            ]
            for name, stream in zip(
                ("standard", "cost_18bp", "delay_5min_9bp"),
                cell["streams"],
                strict=True,
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
                    ("standard", "cost_18bp", "delay_5min_9bp"),
                    cell["streams"],
                    strict=True,
                )
            }
        neighborhood = _neighbor_share(cells, cell)
        oos = observations[0]["development_oos_2024_2025"]
        z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
        gates = {
            "standard_primary": passes_primary(observations[0]),
            "cost_18bp_primary": passes_primary(observations[1]),
            "delay_5min_primary": passes_primary(observations[2]),
            "four_of_five_positive_folds_all_scenarios": all(
                sum(float(item["annualized_return"]) > 0 for item in values) >= 4
                for values in fold_metrics.values()
            ),
            "all_start_dates_positive_all_scenarios": all(
                float(item["annualized_return"]) > 0
                for scenario in starts.values()
                for item in scenario.values()
            ),
            "historical_15pct_mdd_below_20pct_all_scenarios": all(
                float(item["annualized_return"]) >= 0.15 and float(item["max_drawdown"]) < 0.20
                for item in cell["historical"]
            ),
            "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
            "consumed_2026q1_above_5pct": float(observations[0]["consumed_2026q1"]["total_return"])
            > 0.05,
            "consumed_2026_total_above_5pct": float(
                observations[0]["consumed_2026_all"]["total_return"]
            )
            > 0.05,
            "prospective_z_score_at_least_3": passes_global_evidence(z_score),
        }
        definition = {
            "version": cell["version"],
            "mechanism": "v11098_causal_portfolio_volatility_overlay",
            **cell["parameters"],
        }
        records.append(
            {
                "candidate_id": f"lev-v{cell['version']}-"
                + branch.boundary.logical.clock.parent.parent.sparse_veto.campaign._identity(
                    definition
                ),
                "definition": definition,
                "standard": observations[0],
                "cost_18bp": observations[1],
                "delay_5min_9bp": observations[2],
                "historical_scenarios": dict(
                    zip(
                        ("standard", "cost_18bp", "delay_5min_9bp"),
                        cell["historical"],
                        strict=True,
                    )
                ),
                "development_folds": fold_metrics,
                "start_date_stress": starts,
                "neighbor_primary_share": neighborhood,
                "multiple_comparison": {"total_cells": total_cells, "z_score": z_score},
                "gates": gates,
                "strict_pre_factory_null_pass": all(gates.values()),
            }
        )
    records.sort(
        key=lambda item: (
            min(
                float(item[name]["development_oos_2024_2025"]["information_ratio"])
                for name in ("standard", "cost_18bp", "delay_5min_9bp")
            ),
            min(
                float(item[name]["development_oos_2024_2025"]["annualized_return"])
                for name in ("standard", "cost_18bp", "delay_5min_9bp")
            ),
        ),
        reverse=True,
    )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version_range": [FIRST_VERSION, LAST_VERSION],
        "evaluated_cells": len(cells),
        "comparison_cells": total_cells,
        "strict_pre_factory_null_passes": sum(
            item["strict_pre_factory_null_pass"] for item in records
        ),
        "elapsed_seconds": time.perf_counter() - started,
        "records": records,
    }
    v34.v12._atomic(args.output, payload)
    print(
        json.dumps(
            {
                "status": payload["status"],
                "evaluated_cells": payload["evaluated_cells"],
                "strict_pre_factory_null_passes": payload["strict_pre_factory_null_passes"],
                "best": records[0]["candidate_id"],
                "elapsed_seconds": payload["elapsed_seconds"],
            }
        )
    )


if __name__ == "__main__":
    main()
