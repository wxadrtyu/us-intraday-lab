"""Unnumbered diagnostic: same-clock routing over native-null components."""

from __future__ import annotations

import argparse
import json
import math
import time
from datetime import UTC, datetime, timedelta
from datetime import time as wall_time
from pathlib import Path
from zoneinfo import ZoneInfo

import analyze_full_universe_intraday_v53_cross_asset_factors as v53
import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v42_multifactor_vol_target as v42
import evaluate_full_universe_intraday_v47_score_slope as v47
import evaluate_full_universe_intraday_v59_v145_version_campaign as campaign
import numpy as np
import pandas as pd
import search_full_universe_intraday_v12_robustness as v12
import search_full_universe_intraday_v13_regime_rotation as v13
import validate_full_universe_intraday_v246_component_factory_null as native_null

from us_intraday_lab.fast_intraday_research import metrics
from us_intraday_lab.validation.null_tests import (
    HoldingRuleScoringConfig,
    NullOpportunity,
    NullTestConfig,
    run_null_tests,
)
from us_intraday_lab.validation.stability import TQQQ_SOXL_SYMBOLS

EASTERN = ZoneInfo("America/New_York")
CLOCKS = ((17, 47), (23, 65), (29, 72), (35, 69), (41, 75))
MODES = ("max_edge", "asset_consensus")
QUANTILES = tuple(index / 10 for index in range(10))
CUMULATIVE_CELLS = 31_510 + 435 * 8 + 100


def _timestamp(session: object, bar: int) -> datetime:
    date = pd.Timestamp(session).date()
    local = datetime.combine(date, wall_time(9, 30), tzinfo=EASTERN) + timedelta(minutes=5 * bar)
    return local.astimezone(UTC)


def _records(source_dir: Path, audit: dict) -> list[dict]:
    passed = {
        item["component_candidate_id"]
        for item in audit["results"]
        if item["component_factory_null"]["passed"]
    }
    records = []
    for version in range(59, 146):
        payload = json.loads(
            (source_dir / f"full-universe-intraday-v{version}-exact.json").read_text(
                encoding="utf-8"
            )
        )
        records.extend(record for record in payload["records"] if record["candidate_id"] in passed)
    # One representative per true factor/clock/engine family, chosen on training only.
    families: dict[tuple, dict] = {}
    for record in records:
        definition = record["definition"]
        key = (
            tuple(definition["factors"]),
            int(definition["decision"]),
            int(definition["exit"]),
            str(definition["engine"]),
        )
        score = min(
            float(record[name]["train_2022_2023"]["annualized_return"])
            for name in ("standard", "cost_18bp", "delay_5min_9bp")
        )
        if key not in families or score > families[key]["_training_score"]:
            families[key] = {**record, "_training_score": score}
    return list(families.values())


def _model(record: dict) -> campaign.RidgeModel:
    definition, payload = record["definition"], record["model"]
    negative = payload["negative_coefficients"]
    return campaign.RidgeModel(
        tuple(definition["factors"]),
        int(definition["decision"]),
        int(definition["exit"]),
        float(definition["alpha"]),
        np.asarray(payload["mean"]),
        np.asarray(payload["scale"]),
        np.asarray(payload["coefficients"]),
        np.asarray(negative) if negative is not None else None,
        float(payload["threshold"]),
    )


def _cache(
    cube: v53.Cube,
    records: list[dict],
    edge_scales: list[float] | None = None,
) -> list[dict]:
    train = cube.masks()["train_2022_2023"] if edge_scales is None else None
    output = []
    for record_index, record in enumerate(records):
        model = _model(record)
        engine = str(record["definition"]["engine"])
        prediction = campaign._prediction(cube, model)
        selected, active = campaign._signal(cube, model, engine)
        best = np.max(prediction, axis=1)
        if edge_scales is None:
            scale = float(np.std(best[train & np.isfinite(best)], ddof=1))
            if not np.isfinite(scale) or scale < 1e-8:
                scale = 1.0
        else:
            scale = edge_scales[record_index]
        edge = (best - model.threshold) / scale
        edge[~active] = -np.inf
        streams = campaign._streams(
            cube,
            model,
            engine,
            float(record["definition"]["target_volatility"]),
            int(record["definition"]["lookback"]),
        )
        raw = campaign._raw(cube, model, engine, v34.STANDARD_COST, 0)
        exposure = v42._exposure(
            raw.values,
            int(record["definition"]["lookback"]),
            float(record["definition"]["target_volatility"]),
            0.0,
        )
        output.append(
            {
                "candidate_id": record["candidate_id"],
                "definition": record["definition"],
                "selected": selected,
                "active": active,
                "edge": edge,
                "streams": streams,
                "exposure": exposure,
                "edge_scale": scale,
            }
        )
    return output


def _route(
    cube: v53.Cube,
    items: list[dict],
    mode: str,
    quantile: float,
    threshold_override: float | None = None,
) -> dict:
    edges = np.stack([item["edge"] for item in items], axis=1)
    selected_assets = np.stack([item["selected"] for item in items], axis=1)
    finite_edges = np.where(np.isfinite(edges), edges, -1e100)
    if mode == "max_edge":
        chosen = np.argmax(finite_edges, axis=1)
        meta_edge = finite_edges[cube.rows, chosen]
    else:
        support = np.maximum(finite_edges, 0.0)
        tqqq = np.sum(np.where(selected_assets == 3, support, 0.0), axis=1)
        soxl = np.sum(np.where(selected_assets == 4, support, 0.0), axis=1)
        consensus_asset = np.where(tqqq >= soxl, 3, 4)
        eligible = np.where(selected_assets == consensus_asset[:, None], finite_edges, -1e100)
        chosen = np.argmax(eligible, axis=1)
        meta_edge = eligible[cube.rows, chosen]
    if threshold_override is None:
        train = cube.masks()["train_2022_2023"]
        threshold_values = meta_edge[train & (meta_edge > -1e50)]
        threshold = float(np.quantile(threshold_values, quantile))
    else:
        threshold = threshold_override
    active = (meta_edge >= threshold) & (meta_edge > -1e50)
    streams = []
    for scenario in range(3):
        values = np.stack([item["streams"][scenario].values for item in items], axis=1)
        benchmark = np.stack([item["streams"][scenario].benchmark for item in items], axis=1)
        trades = np.stack([item["streams"][scenario].component_trades for item in items], axis=1)
        streams.append(
            v12.ReturnStream(
                np.where(active, values[cube.rows, chosen], 0.0),
                np.where(active, benchmark[cube.rows, chosen], 0.0),
                active,
                np.where(active, trades[cube.rows, chosen], 0),
            )
        )
    chosen_asset = np.stack([item["selected"] for item in items], axis=1)[cube.rows, chosen]
    exposure = np.stack([item["exposure"] for item in items], axis=1)[cube.rows, chosen]
    return {
        "streams": tuple(streams),
        "chosen": chosen,
        "chosen_asset": chosen_asset,
        "exposure": exposure,
        "active": active,
        "threshold": threshold,
    }


def _opportunities(cube: v53.Cube, route: dict, decision: int, exit_bar: int):
    output = []
    development = cube.masks()["development_all"]
    for row in np.flatnonzero(development):
        for asset, symbol in zip(campaign.ASSETS, TQQQ_SOXL_SYMBOLS, strict=True):
            for shift in native_null.TIMESTAMP_SHIFTS:
                entry = decision + 1 + shift
                exit_shifted = exit_bar + shift
                tradable = (
                    0 <= entry < exit_shifted <= 77
                    and cube.first[row, entry, asset] <= entry * 5 + cube.boundary_tolerance
                    and cube.first[row, exit_shifted, asset]
                    <= exit_shifted * 5 + cube.boundary_tolerance
                    and np.isfinite(cube.opens[row, entry, asset])
                    and np.isfinite(cube.opens[row, exit_shifted, asset])
                    and cube.opens[row, entry, asset] > 0
                )
                profit = 0.0
                if tradable:
                    profit = float(
                        route["exposure"][row]
                        * (
                            cube.opens[row, exit_shifted, asset] / cube.opens[row, entry, asset]
                            - 1
                            - v34.STANDARD_COST
                        )
                    )
                session = pd.Timestamp(cube.sessions[row]).date()
                signal_time = _timestamp(cube.sessions[row], entry)
                output.append(
                    NullOpportunity(
                        opportunity_id=f"{session}-{symbol}-meta-shift{shift:+d}",
                        symbol=symbol,
                        session=session,
                        signal_time=signal_time,
                        entry_time=signal_time,
                        exit_time=_timestamp(cube.sessions[row], exit_shifted),
                        entered=bool(
                            shift == 0
                            and route["active"][row]
                            and route["chosen_asset"][row] == asset
                            and tradable
                        ),
                        holding_rule_net_profit=profit,
                    )
                )
    output.sort(key=lambda item: (item.session, item.signal_time, item.symbol))
    return tuple(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    records = _records(args.source_dir, audit)
    development = v53.Cube(args.root, "alpaca", 0)
    historical = v53.Cube(args.root, "historical", 0)
    folds = np.array_split(np.flatnonzero(development.masks()["development_all"]), 5)
    null_config = NullTestConfig(
        seed=native_null.NULL_SEED,
        repetitions=native_null.NULL_REPETITIONS,
        percentile=native_null.NULL_PERCENTILE,
        symbols=TQQQ_SOXL_SYMBOLS,
    )
    null_scoring = HoldingRuleScoringConfig(
        scoring_id="meta-factor-diagnostic-null",
        rule_version="same-clock-meta-factor-router-v1",
        cost_model_id="standard-9bp-v1",
        max_entries_per_session=1,
        max_concurrent_positions=1,
    )
    summaries, all_cells = [], []
    diagnostic_index = 1
    for decision, exit_bar in CLOCKS:
        clock_records = [
            record
            for record in records
            if (int(record["definition"]["decision"]), int(record["definition"]["exit"]))
            == (decision, exit_bar)
        ]
        development_cache = _cache(development, clock_records)
        historical_cache = _cache(
            historical,
            clock_records,
            [item["edge_scale"] for item in development_cache],
        )
        for mode in MODES:
            for quantile in QUANTILES:
                diagnostic_started = time.perf_counter()
                route = _route(development, development_cache, mode, quantile)
                historical_route = _route(
                    historical,
                    historical_cache,
                    mode,
                    quantile,
                    route["threshold"],
                )
                observations = [
                    v47._observe(development, stream, True) for stream in route["streams"]
                ]
                historical_observation = v47._observe(
                    historical, historical_route["streams"][0], True
                )["historical_2018_2020"]
                fold_observations = [
                    metrics(
                        route["streams"][0].values[fold],
                        route["streams"][0].benchmark[fold],
                        route["streams"][0].active[fold],
                    )
                    for fold in folds
                ]
                gates = {
                    "standard_primary": v13._primary(observations[0]),
                    "cost_18bp_primary": v13._primary(observations[1]),
                    "delay_5min_primary": v13._primary(observations[2]),
                    "four_of_five_positive_folds": sum(
                        float(item["annualized_return"]) > 0 for item in fold_observations
                    )
                    >= 4,
                    "historical_positive_mdd_below_20pct": (
                        float(historical_observation["annualized_return"]) > 0
                        and float(historical_observation["max_drawdown"]) < 0.20
                    ),
                    "consumed_2026_total_above_5pct": float(
                        observations[0]["consumed_2026_all"]["total_return"]
                    )
                    > 0.05,
                }
                pre_null = all(gates.values())
                null_payload = None
                if pre_null:
                    result = run_null_tests(
                        _opportunities(development, route, decision, exit_bar),
                        config=null_config,
                        scoring_config=null_scoring,
                    )
                    null_payload = native_null._result_payload(result)
                    gates["factory_native_null"] = result.passed
                else:
                    gates["factory_native_null"] = False
                oos = observations[0]["development_oos_2024_2025"]
                z_score = float(oos["information_ratio"]) * math.sqrt(
                    max(1, int(oos["trades"])) / 252
                )
                adjusted_p = min(1.0, 2.0 * v47._normal_tail(abs(z_score)) * CUMULATIVE_CELLS)
                gates["cumulative_bonferroni_5pct"] = adjusted_p < 0.05
                definition = {
                    "diagnostic_index": diagnostic_index,
                    "strategy": "same_clock_meta_factor_router",
                    "decision": decision,
                    "exit": exit_bar,
                    "mode": mode,
                    "training_activation_quantile": quantile,
                    "component_candidate_ids": [item["candidate_id"] for item in development_cache],
                    "factor_family_count": len(development_cache),
                    "maximum_gross": 1.0,
                    "overnight": False,
                }
                candidate_id = "diag-meta-" + campaign._identity(definition)[:16]
                payload = {
                    "schema_version": "1.0.0",
                    "status": "COMPLETE",
                    "diagnostic_index": diagnostic_index,
                    "candidate_id": candidate_id,
                    "definition": definition,
                    "selection_contract": "component family representatives use training only; 2026 is diagnostic only",
                    "standard": observations[0],
                    "cost_18bp": observations[1],
                    "delay_5min_9bp": observations[2],
                    "historical_2018_2020": historical_observation,
                    "development_folds": fold_observations,
                    "activation_threshold": route["threshold"],
                    "gates": gates,
                    "factory_native_null": null_payload,
                    "multiple_comparison_pressure": {
                        "cells": CUMULATIVE_CELLS,
                        "adjusted_p": adjusted_p,
                        "passed": adjusted_p < 0.05,
                    },
                    "scan": {
                        "evaluated_cells": 1,
                        "elapsed_seconds": time.perf_counter() - diagnostic_started,
                    },
                }
                args.output_dir.mkdir(parents=True, exist_ok=True)
                v12._atomic(
                    args.output_dir / f"meta-factor-diagnostic-{diagnostic_index:03d}.json",
                    payload,
                )
                all_cells.append(payload)
                summaries.append(
                    {
                        "diagnostic_index": diagnostic_index,
                        "candidate_id": candidate_id,
                        "standard_oos": oos["annualized_return"],
                        "cost_oos": observations[1]["development_oos_2024_2025"][
                            "annualized_return"
                        ],
                        "delay_oos": observations[2]["development_oos_2024_2025"][
                            "annualized_return"
                        ],
                        "consumed_2026": observations[0]["consumed_2026_all"]["total_return"],
                        "pre_null_pass": pre_null,
                        "native_null_pass": bool(null_payload and null_payload["passed"]),
                    }
                )
                print(
                    f"d{diagnostic_index:03d} {decision}/{exit_bar} {mode} q={quantile:.1f} "
                    f"oos={oos['annualized_return']:.3f} pre={pre_null} "
                    f"null={bool(null_payload and null_payload['passed'])}",
                    flush=True,
                )
                diagnostic_index += 1
    if diagnostic_index != 101:
        raise RuntimeError(f"diagnostic ended at unexpected index {diagnostic_index}")

    # Immediate activation-quantile neighborhood within each clock/mode sequence.
    for index, payload in enumerate(all_cells):
        peers = [
            item
            for item in all_cells
            if item["definition"]["decision"] == payload["definition"]["decision"]
            and item["definition"]["mode"] == payload["definition"]["mode"]
        ]
        position = peers.index(payload)
        neighbors = peers[max(0, position - 1) : min(len(peers), position + 2)]
        share = sum(
            all(
                item["gates"][name]
                for name in ("standard_primary", "cost_18bp_primary", "delay_5min_primary")
            )
            for item in neighbors
        ) / len(neighbors)
        payload["parameter_neighborhood_primary_share"] = share
        payload["gates"]["parameter_neighborhood_70pct_primary"] = share >= 0.70
        v12._atomic(
            args.output_dir / f"meta-factor-diagnostic-{payload['diagnostic_index']:03d}.json",
            payload,
        )
    summary = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "scope": "unnumbered_meta_factor_diagnostic",
        "diagnostics": 100,
        "evaluated_cells": 100,
        "elapsed_seconds": time.perf_counter() - started,
        "pre_null_passes": sum(item["pre_null_pass"] for item in summaries),
        "native_null_passes": sum(item["native_null_pass"] for item in summaries),
        "records": summaries,
    }
    v12._atomic(args.summary, summary)
    print(json.dumps({key: value for key, value in summary.items() if key != "records"}, indent=2))


if __name__ == "__main__":
    main()
