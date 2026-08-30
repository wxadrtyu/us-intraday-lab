"""v7595: equal-gross ensemble of independently specified loss-veto routes."""

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
import evaluate_full_universe_intraday_v5970_v6069_sector_flow_leadership as sector
import evaluate_full_universe_intraday_v7395_v7494_full_route_loss_veto as base
import evaluate_full_universe_intraday_v7495_v7594_last_bar_loss_veto as last_bar
import numpy as np
import pandas as pd

from us_intraday_lab.fast_intraday_research import metrics

VERSION = 7595
PRIOR_COMPARISON_CELLS = 256_455
NULL_REPETITIONS = 500
NULL_PERCENTILE = 0.95
NULL_SEED = 20260831
SAFE_SHIFT_MINIMUM = 20


def _combine(streams):
    weight = 1.0 / len(streams)
    return v34.v12.ReturnStream(
        sum((stream.values * weight for stream in streams), np.zeros(len(streams[0].values))),
        sum(
            (stream.benchmark * weight for stream in streams),
            np.zeros(len(streams[0].benchmark)),
        ),
        np.logical_or.reduce([stream.active for stream in streams]),
        sum(
            (stream.component_trades for stream in streams),
            np.zeros(len(streams[0].component_trades), dtype=int),
        ),
    )


def _compound(values):
    return float(np.prod(1.0 + values) - 1.0)


def _native_null(route, allowed, variants, development_mask):
    index = np.flatnonzero(development_mask)
    route_values = route.values[index]
    selected = [mask[index] for mask in allowed]
    observed = _compound(_combine([base._veto(route, mask) for mask in allowed]).values[index])
    rng = np.random.default_rng(NULL_SEED)
    permutation_max = []
    shift_max = []
    for _ in range(NULL_REPETITIONS):
        permuted = [mask[rng.permutation(len(index))] for mask in selected]
        shifts = [
            np.roll(mask, int(rng.integers(SAFE_SHIFT_MINIMUM, len(index) - 4)))
            for mask in selected
        ]
        permutation_max.append(
            max(
                _compound(
                    np.mean(
                        [np.where(permuted[item], route_values, 0.0) for item in variant], axis=0
                    )
                )
                for variant in variants
            )
        )
        shift_max.append(
            max(
                _compound(
                    np.mean([np.where(shifts[item], route_values, 0.0) for item in variant], axis=0)
                )
                for variant in variants
            )
        )
    permutation_threshold = float(np.quantile(permutation_max, NULL_PERCENTILE))
    shift_threshold = float(np.quantile(shift_max, NULL_PERCENTILE))
    evidence = {
        "observed_profit": observed,
        "permutation_maxT_95pct": permutation_threshold,
        "safe_shift_maxT_95pct": shift_threshold,
        "seed": NULL_SEED,
        "repetitions": NULL_REPETITIONS,
        "percentile": NULL_PERCENTILE,
    }
    evidence["passed"] = observed > permutation_threshold and observed > shift_threshold
    evidence["evidence_sha256"] = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return evidence


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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    last_bar._configure()
    if base.base.prior.parent._sha(args.source) != base.base.prior.SOURCE_SHA256:
        raise RuntimeError("V42_SOURCE_HASH_CHANGED")
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    if selection["status"] != "COMPLETE" or selection["version_range"] != [7495, 7594]:
        raise RuntimeError("V7495_SELECTION_NOT_FROZEN_COMPLETE")
    selected_records = []
    for family in base.FACTOR_SETS:
        family_records = [
            item for item in selection["records"] if item["definition"]["factor_set"] == family
        ]
        selected_records.append(
            max(
                family_records,
                key=lambda item: base._rank(
                    (item["standard"], item["cost_18bp"], item["delay_5min_9bp"])
                ),
            )
        )
    source = json.loads(args.source.read_text(encoding="utf-8"))
    source_map = {item["candidate_id"]: item for item in source["records"]}
    base.base.prior.cash._configure()
    base_ids = tuple(
        dict.fromkeys(
            (
                base.base.prior.route.MODERN_PARENT,
                base.base.prior.route.TRANSFER_PARENT,
                base.base.prior.cash.FALLBACK_PARENT,
            )
        )
    )
    required = tuple(dict.fromkeys((*base_ids, *base.base.FILL_PARENTS)))
    development = v34.Cube(args.root, "alpaca", 0)
    historical = v34.Cube(args.root, "historical", 0)
    development_factors = sector.SectorFlowLeadershipCube(args.root, "alpaca", 0)
    historical_factors = sector.SectorFlowLeadershipCube(args.root, "historical", 0)
    dev_state = base.base.prior.parent.cross.Cube(args.root, "alpaca", 0)
    hist_state = base.base.prior.parent.cross.Cube(args.root, "historical", 0)
    models = {
        item: v39._models(development, [source_map[item]["definition"]["strategy"]])[0]
        for item in required
    }
    dev_parents = {
        item: base.base.prior.parent._parent_streams(development, source_map[item], models[item])
        for item in required
    }
    hist_parents = {
        item: base.base.prior.parent._parent_streams(historical, source_map[item], models[item])
        for item in required
    }
    core_model = base.base.state._fit_state(dev_state, base.base.CORE_LOW_DISPERSION_TREND, 0.20)
    override_model = base.base.state._fit_state(dev_state, base.base.CORE_OVERSOLD_REPAIR, 0.35)
    _, transfer_state = base.base.prior.route._base_state(dev_state, core_model, override_model)
    gate_model = base.base.prior.route._fit_gate(
        development,
        dev_parents[base.base.prior.route.TRANSFER_PARENT][0],
        transfer_state,
        base.base.prior.route.FACTOR_SETS[base.base.prior.BASE_FAMILY],
        base.base.prior.BASE_QUANTILE,
        base.base.prior.BASE_ALPHA,
    )
    fill_model = base.base.state._fit_state(
        dev_state, base.base.state.STATE_FAMILIES["high_vol_recovery"], 0.20
    )
    dev_route = base._route(
        development, dev_state, dev_parents, core_model, override_model, gate_model, fill_model
    )
    hist_route = base._route(
        historical, hist_state, hist_parents, core_model, override_model, gate_model, fill_model
    )
    dev_allowed, hist_allowed, contracts = [], [], []
    for item in selected_records:
        definition = item["definition"]
        model = base.quality._fit(
            development_factors,
            dev_route[0],
            dev_route[0].active,
            base.FACTOR_SETS[definition["factor_set"]],
            float(definition["score_quantile"]),
            float(definition["ridge_alpha"]),
        )
        dev_score = base.quality._score(development_factors, model)
        hist_score = base.quality._score(historical_factors, model)
        dev_allowed.append(np.isfinite(dev_score) & (dev_score >= model["threshold"]))
        hist_allowed.append(np.isfinite(hist_score) & (hist_score >= model["threshold"]))
        contracts.append(
            {
                "factor_set": definition["factor_set"],
                "score_quantile": definition["score_quantile"],
                "ridge_alpha": definition["ridge_alpha"],
                "source_candidate_id": item["candidate_id"],
            }
        )
    variants = [tuple(range(len(contracts)))] + [
        tuple(index for index in range(len(contracts)) if index != omitted)
        for omitted in range(len(contracts))
    ]
    dev_components = [
        tuple(base._veto(stream, allowed) for stream in dev_route) for allowed in dev_allowed
    ]
    hist_components = [
        tuple(base._veto(stream, allowed) for stream in hist_route) for allowed in hist_allowed
    ]
    cells = []
    for variant in variants:
        streams = tuple(
            _combine([dev_components[index][scenario] for index in variant])
            for scenario in range(3)
        )
        observations = tuple(v47._observe(development, stream, True) for stream in streams)
        cells.append(
            {
                "variant": variant,
                "streams": streams,
                "observations": observations,
                "primary": all(_primary(item) for item in observations),
            }
        )
    full = cells[0]
    streams, observations = full["streams"], full["observations"]
    historical_streams = tuple(
        _combine([hist_components[index][scenario] for index in variants[0]])
        for scenario in range(3)
    )
    historical_obs = tuple(
        v47._observe(historical, stream, True)["historical_2018_2020"]
        for stream in historical_streams
    )
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    fold_metrics = {
        name: [
            metrics(stream.values[index], stream.benchmark[index], stream.active[index])
            for index in folds
        ]
        for name, stream in zip(("standard", "cost_18bp", "delay_5min_9bp"), streams, strict=True)
    }
    starts = {}
    for start in ("2022-01-01", "2023-01-01", "2024-01-01"):
        mask = development.masks()["development_all"] & (development.dates >= pd.Timestamp(start))
        starts[start] = metrics(
            streams[0].values[mask], streams[0].benchmark[mask], streams[0].active[mask]
        )
    neighborhood = sum(item["primary"] for item in cells) / len(cells)
    total_cells = PRIOR_COMPARISON_CELLS + len(cells)
    oos = observations[0]["development_oos_2024_2025"]
    z_score = float(oos["information_ratio"]) * math.sqrt(max(1, int(oos["trades"])) / 252)
    bonferroni = min(1.0, 2.0 * v47._normal_tail(abs(z_score)) * total_cells)
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
    pre_null = all(gates.values())
    native_null = None
    if pre_null:
        native_null = _native_null(
            dev_route[0], dev_allowed, variants, development.masks()["development_all"]
        )
    definition = {
        "version": VERSION,
        "mechanism": "equal_gross_loss_veto_model_ensemble",
        "components": contracts,
        "component_weight": 0.1,
        "gross_limit": 1.0,
    }
    candidate_id = f"lev-v{VERSION}-" + base._identity(definition)
    record = {
        "candidate_id": candidate_id,
        "definition": definition,
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
        "strict_pre_factory_null_pass": pre_null,
        "native_factory_null": native_null,
        "admitted": bool(pre_null and native_null and native_null["passed"]),
    }
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version_range": [VERSION, VERSION],
        "evaluated_cells": len(cells),
        "comparison_cells": total_cells,
        "strict_pre_factory_null_passes": int(pre_null),
        "native_factory_null_runs": int(native_null is not None),
        "native_factory_null_passes": int(bool(native_null and native_null["passed"])),
        "admissions": int(record["admitted"]),
        "elapsed_seconds": time.perf_counter() - started,
        "records": [record],
    }
    v34.v12._atomic(args.output, payload)
    print(
        json.dumps(
            {
                key: payload[key]
                for key in (
                    "status",
                    "strict_pre_factory_null_passes",
                    "native_factory_null_runs",
                    "native_factory_null_passes",
                    "admissions",
                    "elapsed_seconds",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
