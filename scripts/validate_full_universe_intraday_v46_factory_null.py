"""Factory-native null validation under the revised 2026 weak-market diagnostic gate."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime, timedelta
from datetime import time as wall_time
from pathlib import Path
from zoneinfo import ZoneInfo

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v42_multifactor_vol_target as v42
import evaluate_full_universe_intraday_v44_multihorizon_confirmation as v44
import evaluate_full_universe_intraday_v45_event_trigger_multifactor as v45
import numpy as np
import pandas as pd
import search_full_universe_intraday_v12_robustness as v12

from us_intraday_lab.validation.null_tests import (
    HoldingRuleScoringConfig,
    NullOpportunity,
    NullTestConfig,
    run_null_tests,
)
from us_intraday_lab.validation.stability import TQQQ_SOXL_SYMBOLS

WEAK_MARKET_2026_MIN_TOTAL_RETURN = 0.05
NULL_REPETITIONS = 200
NULL_PERCENTILE = 0.95
NULL_SEED = 20_260_816
EASTERN = ZoneInfo("America/New_York")


def _trigger(
    cube: v34.Cube,
    models: list[v44.HorizonModel],
    exit_bar: int,
    weighting: str,
    threshold: float,
    confirmations: int,
    score_delta_floor: float | None,
):
    selected = np.full(len(cube.sessions), -1, dtype=int)
    decision_bar = np.full(len(cube.sessions), -1, dtype=int)
    previous_asset = np.full(len(cube.sessions), -1, dtype=int)
    previous_above = np.zeros(len(cube.sessions), dtype=bool)
    previous_score = None
    assets = np.asarray(v44.ASSETS)
    for model in models:
        score = v45._score(cube, model, exit_bar, weighting)
        local = np.argmax(score, axis=1)
        best_asset = assets[local]
        best_score = score[cube.rows, local]
        above = np.isfinite(best_score) & (best_score >= threshold)
        trigger = (selected < 0) & above
        if score_delta_floor is not None:
            if previous_score is None:
                trigger[:] = False
            else:
                prior_for_asset = previous_score[cube.rows, local]
                delta_score = np.full(len(cube.sessions), np.nan)
                finite_delta = np.isfinite(best_score) & np.isfinite(prior_for_asset)
                np.subtract(
                    best_score,
                    prior_for_asset,
                    out=delta_score,
                    where=finite_delta,
                )
                trigger &= finite_delta & (delta_score >= score_delta_floor)
        if confirmations == 2:
            trigger &= previous_above & (previous_asset == best_asset)
        selected[trigger] = best_asset[trigger]
        decision_bar[trigger] = model.decision
        previous_asset = best_asset
        previous_above = above
        previous_score = score
    return selected, decision_bar


def _timestamp(session: object, bar: int) -> datetime:
    session_date = pd.Timestamp(session).date()
    local = datetime.combine(session_date, wall_time(9, 30), tzinfo=EASTERN) + timedelta(
        minutes=5 * bar
    )
    return local.astimezone(UTC)


def _opportunities(
    cube: v34.Cube,
    models: list[v44.HorizonModel],
    definition: dict,
):
    exit_bar = int(definition["exit"])
    selected, selected_decision = _trigger(
        cube,
        models,
        exit_bar,
        str(definition["weighting"]),
        float(definition["score_threshold"]),
        int(definition["confirmations"]),
        (float(definition["score_delta_floor"]) if "score_delta_floor" in definition else None),
    )
    raw = v45._stream(
        cube,
        models,
        exit_bar,
        str(definition["weighting"]),
        float(definition["score_threshold"]),
        int(definition["confirmations"]),
        v34.STANDARD_COST,
        0,
        score_delta_floor=(
            float(definition["score_delta_floor"]) if "score_delta_floor" in definition else None
        ),
    )
    exposure = v42._exposure(
        raw.values,
        int(definition["lookback"]),
        float(definition["target_volatility"]),
        0.0,
    )
    development = cube.masks()["development_all"]
    output = []
    for row in np.flatnonzero(development):
        for decision in tuple(int(value) for value in definition["horizons"]):
            entry = decision + 1
            for asset, symbol in zip(v44.ASSETS, TQQQ_SOXL_SYMBOLS, strict=True):
                prices_finite = (
                    np.isfinite(cube.opens[row, entry, asset])
                    and np.isfinite(cube.opens[row, exit_bar, asset])
                    and cube.opens[row, entry, asset] > 0
                )
                net_profit = 0.0
                if prices_finite:
                    net_profit = float(
                        exposure[row]
                        * (
                            cube.opens[row, exit_bar, asset] / cube.opens[row, entry, asset]
                            - 1.0
                            - v34.STANDARD_COST
                        )
                    )
                signal_time = _timestamp(cube.sessions[row], entry)
                output.append(
                    NullOpportunity(
                        opportunity_id=(
                            f"{pd.Timestamp(cube.sessions[row]).date().isoformat()}-"
                            f"{symbol}-d{decision}"
                        ),
                        symbol=symbol,
                        session=pd.Timestamp(cube.sessions[row]).date(),
                        signal_time=signal_time,
                        entry_time=signal_time,
                        exit_time=_timestamp(cube.sessions[row], exit_bar),
                        entered=bool(selected[row] == asset and selected_decision[row] == decision),
                        holding_rule_net_profit=net_profit,
                    )
                )
    output.sort(key=lambda item: (item.session, item.signal_time, item.symbol, item.opportunity_id))
    return tuple(output)


def _result_payload(result):
    return {
        "passed": result.passed,
        "reason_code": result.reason_code,
        "observed_profit": result.observed_profit,
        "observed_accepted_entries": result.observed_score.accepted_entry_count,
        "seed": result.seed,
        "repetitions": result.repetitions,
        "percentile": result.percentile,
        "evidence_sha256": result.evidence_sha256,
        "framework_operation_bound": result.framework_operation_bound,
        "distributions": [
            {
                "method": item.method,
                "percentile_threshold": item.percentile_threshold,
                "maximum": max(item.statistics),
                "mean": float(np.mean(item.statistics)),
            }
            for item in result.distributions
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    candidates = []
    for item in source["records"]:
        gates = item["gates"]
        economic = all(
            gates[name]
            for name in (
                "standard_primary",
                "cost_18bp_primary",
                "delay_5min_primary",
                "four_of_five_positive_folds",
                "historical_positive_mdd_below_20pct",
            )
        )
        weak_market = (
            float(item["standard"]["consumed_2026_all"]["total_return"])
            > WEAK_MARKET_2026_MIN_TOTAL_RETURN
        )
        if economic and weak_market:
            candidates.append(item)
    cube = v34.Cube(args.root, "alpaca", 0)
    results = []
    scoring = HoldingRuleScoringConfig(
        scoring_id="v46-event-trigger-null",
        rule_version="v45-first-crossing-four-factor-v1",
        cost_model_id="standard-9bp-v1",
        max_entries_per_session=1,
        max_concurrent_positions=1,
    )
    config = NullTestConfig(
        seed=NULL_SEED,
        repetitions=NULL_REPETITIONS,
        percentile=NULL_PERCENTILE,
        symbols=TQQQ_SOXL_SYMBOLS,
    )
    for item in candidates:
        definition = item["definition"]
        models = v44._fit(
            cube,
            tuple(int(value) for value in definition["horizons"]),
            int(definition["exit"]),
        )
        if models is None:
            raise RuntimeError("frozen event-trigger candidate no longer fits")
        result = run_null_tests(
            _opportunities(cube, models, definition),
            config=config,
            scoring_config=scoring,
        )
        results.append(
            {
                "candidate_id": item["candidate_id"],
                "definition": definition,
                "development_rank": item["development_rank"],
                "consumed_2026_total_return": item["standard"]["consumed_2026_all"]["total_return"],
                "factory_null": _result_payload(result),
                "revised_2026_weak_market_gate": True,
                "eligible_before_neighborhood": result.passed,
            }
        )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_contract": (
            "candidate family was frozen on 2022-2025; consumed 2026 only applies the "
            "predeclared greater-than-5-percent weak-market diagnostic"
        ),
        "revised_2026_gate": {
            "metric": "consumed_2026_all.total_return",
            "operator": ">",
            "threshold": WEAK_MARKET_2026_MIN_TOTAL_RETURN,
        },
        "null_contract": {
            "methods": ["SESSION_SIGNAL_PERMUTATION", "SESSION_SAFE_TIMESTAMP_SHIFT"],
            "repetitions": NULL_REPETITIONS,
            "percentile": NULL_PERCENTILE,
            "seed": NULL_SEED,
        },
        "candidate_count": len(results),
        "factory_null_passes": sum(item["factory_null"]["passed"] for item in results),
        "elapsed_seconds": time.perf_counter() - started,
        "results": results,
    }
    v12._atomic(args.output, payload)
    print(
        json.dumps(
            {
                "candidate_count": payload["candidate_count"],
                "factory_null_passes": payload["factory_null_passes"],
                "elapsed_seconds": payload["elapsed_seconds"],
                "results": [
                    {
                        "candidate_id": item["candidate_id"],
                        "passed": item["factory_null"]["passed"],
                        "observed_profit": item["factory_null"]["observed_profit"],
                        "thresholds": [
                            value["percentile_threshold"]
                            for value in item["factory_null"]["distributions"]
                        ],
                    }
                    for item in results
                ],
            }
        )
    )


if __name__ == "__main__":
    main()
