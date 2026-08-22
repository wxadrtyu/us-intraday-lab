"""Factory-native null validation for the frozen v650 reversal component."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime, timedelta
from datetime import time as wall_time
from pathlib import Path
from zoneinfo import ZoneInfo

import evaluate_full_universe_intraday_v248_v347_mechanism_campaign as prior
import numpy as np
import pandas as pd

from us_intraday_lab.validation.null_tests import (
    HoldingRuleScoringConfig,
    NullOpportunity,
    NullTestConfig,
    run_null_tests,
)
from us_intraday_lab.validation.stability import TQQQ_SOXL_SYMBOLS

EASTERN = ZoneInfo("America/New_York")
SHIFTS = (-3, -2, -1, 0, 1, 2, 3)


def _timestamp(session: object, bar: int) -> datetime:
    local = datetime.combine(
        pd.Timestamp(session).date(), wall_time(9, 30), tzinfo=EASTERN
    ) + timedelta(minutes=5 * bar)
    return local.astimezone(UTC)


def _opportunities(cube: prior.v53.Cube, selection: dict) -> tuple[NullOpportunity, ...]:
    definition = selection["component_definition"]
    model = selection["component_model"]
    mean = np.asarray(model["mean"])
    scale = np.asarray(model["scale"])
    decision = int(definition["decision"])
    exit_bar = int(definition["exit"])
    factors = tuple(definition["factors"])
    directions = tuple(int(value) for value in definition["directions"])
    score = prior._rule_score(cube, decision, factors, directions, mean, scale)
    local = np.argmax(score, axis=1)
    selected = prior.ASSETS[local]
    best = score[cube.rows, local]
    active = np.isfinite(best) & (best >= float(definition["score_threshold"]))
    if int(definition["confirmations"]) == 2:
        earlier = prior._rule_score(cube, decision - 3, factors, directions, mean, scale)
        earlier_local = np.argmax(earlier, axis=1)
        earlier_best = earlier[cube.rows, earlier_local]
        active &= (
            (prior.ASSETS[earlier_local] == selected)
            & np.isfinite(earlier_best)
            & (earlier_best >= float(definition["score_threshold"]))
        )
    raw = prior._rule_raw(
        cube,
        definition,
        mean,
        scale,
        float(definition["score_threshold"]),
        prior.v34.STANDARD_COST,
        0,
    )
    exposure = prior.v42._exposure(
        raw.values,
        int(definition["lookback"]),
        float(definition["target_volatility"]),
        0.0,
    )
    entry = decision + 1
    output = []
    for row in np.flatnonzero(cube.masks()["development_all"]):
        session = pd.Timestamp(cube.sessions[row]).date()
        for asset, symbol in zip(prior.ASSETS, TQQQ_SOXL_SYMBOLS, strict=True):
            for shift in SHIFTS:
                shifted_entry = entry + shift
                shifted_exit = exit_bar + shift
                tradable = (
                    0 <= shifted_entry < shifted_exit <= 77
                    and cube.first[row, shifted_entry, asset]
                    <= shifted_entry * 5 + cube.boundary_tolerance
                    and cube.first[row, shifted_exit, asset]
                    <= shifted_exit * 5 + cube.boundary_tolerance
                    and np.isfinite(cube.opens[row, shifted_entry, asset])
                    and np.isfinite(cube.opens[row, shifted_exit, asset])
                    and cube.opens[row, shifted_entry, asset] > 0
                )
                net_profit = 0.0
                if tradable:
                    net_profit = float(
                        exposure[row]
                        * (
                            cube.opens[row, shifted_exit, asset]
                            / cube.opens[row, shifted_entry, asset]
                            - 1.0
                            - prior.v34.STANDARD_COST
                        )
                    )
                output.append(
                    NullOpportunity(
                        opportunity_id=f"{session}-{symbol}-v650-shift{shift:+d}",
                        symbol=symbol,
                        session=session,
                        signal_time=_timestamp(cube.sessions[row], shifted_entry),
                        entry_time=_timestamp(cube.sessions[row], shifted_entry),
                        exit_time=_timestamp(cube.sessions[row], shifted_exit),
                        entered=bool(
                            shift == 0 and active[row] and selected[row] == asset and tradable
                        ),
                        holding_rule_net_profit=net_profit,
                    )
                )
    output.sort(key=lambda item: (item.session, item.signal_time, item.symbol))
    return tuple(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    if not selection["pre_factory_null_pass"]:
        raise RuntimeError("V650_NOT_ELIGIBLE_FOR_COMPONENT_NULL")
    cube = prior.v53.Cube(args.root, "alpaca", 0)
    result = run_null_tests(
        _opportunities(cube, selection),
        config=NullTestConfig(
            seed=20_260_822,
            repetitions=200,
            percentile=0.95,
            symbols=TQQQ_SOXL_SYMBOLS,
        ),
        scoring_config=HoldingRuleScoringConfig(
            scoring_id="v651-reversal-component-null",
            rule_version="v580-prior-weak-reversal-v1",
            cost_model_id="standard-9bp-v1",
            max_entries_per_session=1,
            max_concurrent_positions=1,
        ),
    )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version": 651,
        "candidate_id": selection["candidate_id"],
        "component_candidate_id": selection["component_candidate_id"],
        "factory_null": {
            "passed": result.passed,
            "reason_code": result.reason_code,
            "observed_profit": result.observed_profit,
            "observed_accepted_entries": result.observed_score.accepted_entry_count,
            "seed": result.seed,
            "repetitions": result.repetitions,
            "percentile": result.percentile,
            "evidence_sha256": result.evidence_sha256,
            "distributions": [
                {
                    "method": item.method,
                    "percentile_threshold": item.percentile_threshold,
                    "maximum": max(item.statistics),
                    "mean": float(np.mean(item.statistics)),
                }
                for item in result.distributions
            ],
        },
        "eligible_after_factory_null": bool(result.passed),
        "elapsed_seconds": time.perf_counter() - started,
    }
    prior.v12._atomic(args.output, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
