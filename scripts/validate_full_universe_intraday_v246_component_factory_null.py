"""v246: factory-native null validation for anchored-ensemble component sleeves."""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime, timedelta
from datetime import time as wall_time
from pathlib import Path
from zoneinfo import ZoneInfo

import analyze_full_universe_intraday_v53_cross_asset_factors as v53
import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v42_multifactor_vol_target as v42
import evaluate_full_universe_intraday_v59_v145_version_campaign as campaign
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

EASTERN = ZoneInfo("America/New_York")
NULL_REPETITIONS = 200
NULL_PERCENTILE = 0.95
NULL_SEED = 20_260_816
TIMESTAMP_SHIFTS = (-3, -2, -1, 0, 1, 2, 3)


def _timestamp(session: object, bar: int) -> datetime:
    session_date = pd.Timestamp(session).date()
    local = datetime.combine(session_date, wall_time(9, 30), tzinfo=EASTERN) + timedelta(
        minutes=5 * bar
    )
    return local.astimezone(UTC)


def _opportunities(cube: v53.Cube, record: dict) -> tuple[NullOpportunity, ...]:
    definition = record["definition"]
    model = campaign.RidgeModel(
        tuple(definition["factors"]),
        int(definition["decision"]),
        int(definition["exit"]),
        float(definition["alpha"]),
        np.asarray(record["model"]["mean"]),
        np.asarray(record["model"]["scale"]),
        np.asarray(record["model"]["coefficients"]),
        (
            np.asarray(record["model"]["negative_coefficients"])
            if record["model"]["negative_coefficients"] is not None
            else None
        ),
        float(record["model"]["threshold"]),
    )
    engine = str(definition["engine"])
    selected, active = campaign._signal(cube, model, engine)
    raw = campaign._raw(cube, model, engine, v34.STANDARD_COST, 0)
    exposure = v42._exposure(
        raw.values,
        int(definition["lookback"]),
        float(definition["target_volatility"]),
        0.0,
    )
    entry = model.decision + 1
    development = cube.masks()["development_all"]
    output = []
    for row in np.flatnonzero(development):
        for asset, symbol in zip(campaign.ASSETS, TQQQ_SOXL_SYMBOLS, strict=True):
            for shift in TIMESTAMP_SHIFTS:
                shifted_entry = entry + shift
                shifted_exit = model.exit_bar + shift
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
                            - v34.STANDARD_COST
                        )
                    )
                session = pd.Timestamp(cube.sessions[row]).date()
                signal_time = _timestamp(cube.sessions[row], shifted_entry)
                output.append(
                    NullOpportunity(
                        opportunity_id=(
                            f"{session.isoformat()}-{symbol}-component-shift{shift:+d}"
                        ),
                        symbol=symbol,
                        session=session,
                        signal_time=signal_time,
                        entry_time=signal_time,
                        exit_time=_timestamp(cube.sessions[row], shifted_exit),
                        entered=bool(
                            shift == 0 and active[row] and selected[row] == asset and tradable
                        ),
                        holding_rule_net_profit=net_profit,
                    )
                )
    output.sort(key=lambda item: (item.session, item.signal_time, item.symbol))
    return tuple(output)


def _result_payload(result) -> dict:
    return {
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
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--component-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    ensemble_candidates = []
    for version in range(146, 246):
        payload = json.loads(
            (args.source_dir / f"full-universe-intraday-v{version}-exact.json").read_text(
                encoding="utf-8"
            )
        )
        ensemble_candidates.extend(
            record for record in payload["records"] if record["pre_factory_null_pass"]
        )
    component_records = {}
    for version in range(59, 146):
        payload = json.loads(
            (args.component_dir / f"full-universe-intraday-v{version}-exact.json").read_text(
                encoding="utf-8"
            )
        )
        component_records.update({record["candidate_id"]: record for record in payload["records"]})
    cube = v53.Cube(args.root, "alpaca", 0)
    config = NullTestConfig(
        seed=NULL_SEED,
        repetitions=NULL_REPETITIONS,
        percentile=NULL_PERCENTILE,
        symbols=TQQQ_SOXL_SYMBOLS,
    )
    scoring = HoldingRuleScoringConfig(
        scoring_id="v246-component-null",
        rule_version="development-ranked-ridge-component-v1",
        cost_model_id="standard-9bp-v1",
        max_entries_per_session=1,
        max_concurrent_positions=1,
    )
    results = []
    for ensemble in ensemble_candidates:
        component_id = ensemble["definition"]["component_candidate_id"]
        result = run_null_tests(
            _opportunities(cube, component_records[component_id]),
            config=config,
            scoring_config=scoring,
        )
        results.append(
            {
                "ensemble_candidate_id": ensemble["candidate_id"],
                "component_candidate_id": component_id,
                "v45_weight": ensemble["definition"]["v45_weight"],
                "component_weight": ensemble["definition"]["component_weight"],
                "component_factory_null": _result_payload(result),
            }
        )
    output = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version": 246,
        "validation_scope": (
            "factory-native marginal null validation of each development-selected component; "
            "the user-authorized v45 exception remains separately disclosed"
        ),
        "candidate_count": len(results),
        "factory_null_passes": sum(item["component_factory_null"]["passed"] for item in results),
        "elapsed_seconds": time.perf_counter() - started,
        "results": results,
    }
    v12._atomic(args.output, output)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
