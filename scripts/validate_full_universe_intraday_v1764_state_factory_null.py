"""v1764: native factory nulls for frozen v1664-v1763 state survivors."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v44_multihorizon_confirmation as v44
import evaluate_full_universe_intraday_v248_v347_mechanism_campaign as state_campaign
import evaluate_full_universe_intraday_v1664_v1763_preregistered_campaign as config
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


def _pre_null_candidates(source_dir: Path) -> list[dict]:
    candidates = []
    for version in range(1664, 1764):
        path = source_dir / f"full-universe-intraday-v{version}-exact.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        candidates.extend(
            record for record in payload["records"] if record["pre_factory_null_pass"]
        )
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    candidates = _pre_null_candidates(args.source_dir)
    if not candidates:
        raise RuntimeError("v1764 requires at least one frozen pre-null candidate")
    coefficients_by_name = dict(config.campaign.STATE_CONCEPTS)
    cube = v34.Cube(args.root, "alpaca", 0)
    models = v44._fit(cube, (20, 23, 26, 29), 72)
    base_definition = {
        "horizons": [20, 23, 26, 29],
        "exit": 72,
        "weighting": "reliability",
        "score_threshold": 0.75,
        "confirmations": 2,
        "target_volatility": 0.35,
        "lookback": 15,
    }
    state_cube = state_campaign.v53.Cube(args.root, "alpaca", 0)
    train = state_cube.masks()["train_2022_2023"]
    results = []
    for candidate in candidates:
        definition = candidate["definition"]
        mechanism = str(definition["mechanism"])
        clock = str(definition["clock"])
        coefficients = coefficients_by_name[mechanism]
        matrix = state_campaign._state_matrix(state_cube, clock)
        means = {factor: float(np.nanmean(matrix[factor][train])) for factor in coefficients}
        scales = {
            factor: max(1e-8, float(np.nanstd(matrix[factor][train]))) for factor in coefficients
        }
        score = state_campaign._state_score(matrix, coefficients, means, scales)
        threshold = float(definition["threshold"])
        allowed_sessions = {
            pd.Timestamp(state_cube.sessions[index]).date()
            for index in np.flatnonzero(np.isfinite(score) & (score >= threshold))
        }
        opportunities = tuple(
            opportunity
            for opportunity in v46._opportunities(cube, models, base_definition)
            if opportunity.session in allowed_sessions
        )
        result = run_null_tests(
            opportunities,
            config=NullTestConfig(
                seed=20260826,
                repetitions=v46.NULL_REPETITIONS,
                percentile=v46.NULL_PERCENTILE,
                symbols=TQQQ_SOXL_SYMBOLS,
            ),
            scoring_config=HoldingRuleScoringConfig(
                scoring_id=f"v1764-{candidate['candidate_id']}-state-null",
                rule_version=f"{mechanism}-{clock}-v1",
                cost_model_id="standard-9bp-v1",
                max_entries_per_session=1,
                max_concurrent_positions=1,
            ),
        )
        results.append(
            {
                "candidate_id": candidate["candidate_id"],
                "definition": definition,
                "allowed_development_sessions": len(allowed_sessions),
                "opportunity_count": len(opportunities),
                "factory_null": v46._result_payload(result),
                "global_bonferroni_passed": False,
                "eligible_after_all_gates": False,
            }
        )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version": 1764,
        "selection_contract": "v1664-v1763 frontiers froze on 2022-2025 before native null; 2026 remains consumed diagnostic",
        "candidate_count": len(results),
        "factory_null_passes": sum(item["factory_null"]["passed"] for item in results),
        "admitted_candidates": 0,
        "results": results,
        "elapsed_seconds": time.perf_counter() - started,
    }
    v12._atomic(args.output, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
