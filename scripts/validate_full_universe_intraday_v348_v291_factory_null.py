"""v348: factory-native null validation of the frozen v291 state filter."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v44_multihorizon_confirmation as v44
import evaluate_full_universe_intraday_v248_v347_mechanism_campaign as campaign
import numpy as np
import pandas as pd
import search_full_universe_intraday_v12_robustness as v12
import validate_full_universe_intraday_v46_factory_null as v46

from us_intraday_lab.validation.null_tests import (
    HoldingRuleScoringConfig,
    NullTestConfig,
    run_null_tests,
)
from us_intraday_lab.validation.stability import TQQQ_SOXL_SYMBOLS


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    source = json.loads(args.source.read_text(encoding="utf-8"))
    candidate = next(record for record in source["records"] if record["pre_factory_null_pass"])
    cube = v34.Cube(args.root, "alpaca", 0)
    models = v44._fit(cube, (20, 23, 26, 29), 72)
    definition = {
        "horizons": [20, 23, 26, 29],
        "exit": 72,
        "weighting": "reliability",
        "score_threshold": 0.75,
        "confirmations": 2,
        "target_volatility": 0.35,
        "lookback": 15,
    }
    state_cube = campaign.v53.Cube(args.root, "alpaca", 0)
    matrix = campaign._state_matrix(state_cube, "prior_close")
    train = state_cube.masks()["train_2022_2023"]
    values = matrix["risk_asset_agreement"]
    mean = float(np.nanmean(values[train]))
    scale = max(1e-8, float(np.nanstd(values[train])))
    score = -(values - mean) / scale
    threshold = float(candidate["definition"]["threshold"])
    allowed_sessions = {
        pd.Timestamp(state_cube.sessions[index]).date()
        for index in np.flatnonzero(np.isfinite(score) & (score >= threshold))
    }
    opportunities = tuple(
        opportunity
        for opportunity in v46._opportunities(cube, models, definition)
        if opportunity.session in allowed_sessions
    )
    result = run_null_tests(
        opportunities,
        config=NullTestConfig(
            seed=v46.NULL_SEED,
            repetitions=v46.NULL_REPETITIONS,
            percentile=v46.NULL_PERCENTILE,
            symbols=TQQQ_SOXL_SYMBOLS,
        ),
        scoring_config=HoldingRuleScoringConfig(
            scoring_id="v348-v291-state-filter-null",
            rule_version="v45-prior-risk-agreement-low-v1",
            cost_model_id="standard-9bp-v1",
            max_entries_per_session=1,
            max_concurrent_positions=1,
        ),
    )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version": 348,
        "candidate_id": candidate["candidate_id"],
        "selection_contract": (
            "v291 was frozen on 2022-2025 before this factory-native null test; consumed 2026 "
            "is diagnostic only"
        ),
        "allowed_development_sessions": len(allowed_sessions),
        "opportunity_count": len(opportunities),
        "factory_null": v46._result_payload(result),
        "eligible_after_factory_null": bool(result.passed),
        "elapsed_seconds": time.perf_counter() - started,
    }
    v12._atomic(args.output, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
