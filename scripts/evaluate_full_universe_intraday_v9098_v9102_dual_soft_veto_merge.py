"""v9098-v9102 preregistered convex merge of two admitted soft-veto families."""

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
import evaluate_full_universe_intraday_v8997_v9096_soft_sparse_gap_veto as soft
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics
from us_intraday_lab.prospective_admission_policy import passes_global_evidence

FIRST_VERSION = 9098
LAST_VERSION = 9102
PRIOR_COMPARISON_CELLS = 257_977
UNSTABLE_ID = "lev-v9022-e29ae7b811678f13"
ABSORPTION_ID = "lev-v9083-fade6a99e0b4fa2c"
UNSTABLE_WEIGHTS = (0.30, 0.40, 0.50, 0.60, 0.70)
PRIMARY_WEIGHT = 0.50


def _identity(definition: dict) -> str:
    payload = json.dumps(definition, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def _stream(route, exposure):
    return v34.v12.ReturnStream(
        route.values * exposure,
        route.benchmark * exposure,
        route.active,
        route.component_trades,
    )


def _blend_exposure(unstable, absorption, unstable_weight: float):
    return unstable_weight * unstable + (1.0 - unstable_weight) * absorption


def _primary(observation: dict) -> bool:
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


def _context(root: Path, source_path: Path, selection_path: Path):
    soft._configure()
    campaign = soft.sparse_veto.campaign
    if campaign.base.prior.parent._sha(source_path) != campaign.base.prior.SOURCE_SHA256:
        raise RuntimeError("V9098_SOURCE_HASH_CHANGED")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
    if selection.get("status") != "COMPLETE" or selection.get("version_range") != [8997, 9096]:
        raise RuntimeError("V9098_PARENT_SELECTION_NOT_FROZEN_COMPLETE")
    selected = {item["candidate_id"]: item for item in selection["records"]}
    if not {UNSTABLE_ID, ABSORPTION_ID}.issubset(selected):
        raise RuntimeError("V9098_PARENT_IDS_CHANGED")

    source = json.loads(source_path.read_text(encoding="utf-8"))
    source_map = {item["candidate_id"]: item for item in source["records"]}
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
        item: campaign.base.prior.parent._parent_streams(development, source_map[item], models[item])
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
    _, transfer_state = campaign.base.prior.route._base_state(
        dev_state, core_model, override_model
    )
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
    dev_route = campaign._route(
        development, dev_state, dev_parents, core_model, override_model, gate_model, fill_model
    )
    hist_route = campaign._route(
        historical, hist_state, hist_parents, core_model, override_model, gate_model, fill_model
    )

    dev_exposures, hist_exposures = {}, {}
    for candidate_id in (UNSTABLE_ID, ABSORPTION_ID):
        definition = selected[candidate_id]["definition"]
        model = quality._fit(
            dev_factors,
            dev_route[0],
            dev_route[0].active,
            campaign.FACTOR_SETS[definition["factor_set"]],
            float(definition["score_quantile"]),
            float(definition["ridge_alpha"]),
        )
        dev_score = quality._score(dev_factors, model)
        hist_score = quality._score(hist_factors, model)
        dev_exposures[candidate_id] = np.where(
            np.isfinite(dev_score) & (dev_score >= model["threshold"]), 1.0, soft.LOW_EXPOSURE
        )
        hist_exposures[candidate_id] = np.where(
            np.isfinite(hist_score) & (hist_score >= model["threshold"]), 1.0, soft.LOW_EXPOSURE
        )
    return development, historical, dev_route, hist_route, dev_exposures, hist_exposures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if len(UNSTABLE_WEIGHTS) != LAST_VERSION - FIRST_VERSION + 1:
        raise RuntimeError("V9098_PREREGISTRATION_MISMATCH")
    started = time.perf_counter()
    development, historical, dev_route, hist_route, dev_exp, hist_exp = _context(
        args.root, args.source, args.selection
    )
    cells = []
    for offset, weight in enumerate(UNSTABLE_WEIGHTS):
        dev_exposure = _blend_exposure(dev_exp[UNSTABLE_ID], dev_exp[ABSORPTION_ID], weight)
        hist_exposure = _blend_exposure(hist_exp[UNSTABLE_ID], hist_exp[ABSORPTION_ID], weight)
        streams = tuple(_stream(route, dev_exposure) for route in dev_route)
        hist_streams = tuple(_stream(route, hist_exposure) for route in hist_route)
        observations = tuple(v47._observe(development, stream, True) for stream in streams)
        hist_obs = tuple(
            v47._observe(historical, stream, True)["historical_2018_2020"]
            for stream in hist_streams
        )
        cells.append(
            {
                "version": FIRST_VERSION + offset,
                "weight": weight,
                "streams": streams,
                "observations": observations,
                "hist_obs": hist_obs,
                "primary": all(_primary(item) for item in observations),
            }
        )

    total_cells = PRIOR_COMPARISON_CELLS + len(cells)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    records = []
    for cell in cells:
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
        neighbors = [
            item for item in cells if abs(float(item["weight"]) - float(cell["weight"])) <= 0.100001
        ]
        neighborhood = sum(item["primary"] for item in neighbors) / len(neighbors)
        oos = observations[0]["development_oos_2024_2025"]
        z_score = float(oos["information_ratio"]) * math.sqrt(
            max(1, int(oos["trades"])) / 252
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
                for item in cell["hist_obs"]
            ),
            "parameter_neighborhood_70pct_primary": neighborhood >= 0.70,
            "consumed_2026q1_above_5pct": float(
                observations[0]["consumed_2026q1"]["total_return"]
            ) > 0.05,
            "consumed_2026_total_above_5pct": float(
                observations[0]["consumed_2026_all"]["total_return"]
            ) > 0.05,
            "prospective_z_score_at_least_3": passes_global_evidence(z_score),
        }
        definition = {
            "version": cell["version"],
            "mechanism": "convex_merge_of_two_native_null_admitted_soft_veto_exposures",
            "unstable_reclaim_parent": UNSTABLE_ID,
            "relative_absorption_parent": ABSORPTION_ID,
            "unstable_reclaim_weight": cell["weight"],
            "relative_absorption_weight": 1.0 - cell["weight"],
            "preregistered_primary": cell["weight"] == PRIMARY_WEIGHT,
        }
        records.append(
            {
                "candidate_id": f"lev-v{cell['version']}-" + _identity(definition),
                "definition": definition,
                "standard": observations[0],
                "cost_18bp": observations[1],
                "delay_5min_9bp": observations[2],
                "historical_scenarios": dict(
                    zip(
                        ("standard", "cost_18bp", "delay_5min_9bp"),
                        cell["hist_obs"],
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
    primary = next(item for item in records if item["definition"]["preregistered_primary"])
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version_range": [FIRST_VERSION, LAST_VERSION],
        "evaluated_cells": len(cells),
        "comparison_cells": total_cells,
        "strict_pre_factory_null_passes": sum(
            item["strict_pre_factory_null_pass"] for item in records
        ),
        "preregistered_primary_candidate": primary["candidate_id"],
        "preregistered_primary_pre_null_pass": primary["strict_pre_factory_null_pass"],
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
                "primary": primary["candidate_id"],
                "primary_pre_null_pass": primary["strict_pre_factory_null_pass"],
                "elapsed_seconds": payload["elapsed_seconds"],
            }
        )
    )


if __name__ == "__main__":
    main()
