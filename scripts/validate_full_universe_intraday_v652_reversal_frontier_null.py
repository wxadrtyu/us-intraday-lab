"""Apply the v651 native null to every frozen v580 frontier record."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import evaluate_full_universe_intraday_v248_v347_mechanism_campaign as prior
import numpy as np
import validate_full_universe_intraday_v651_reversal_component_null as validation

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
    cube = prior.v53.Cube(args.root, "alpaca", 0)
    results = []
    for record in source["records"]:
        selection = {
            "component_definition": record["definition"],
            "component_model": record["model"],
        }
        result = run_null_tests(
            validation._opportunities(cube, selection),
            config=NullTestConfig(
                seed=20_260_822,
                repetitions=200,
                percentile=0.95,
                symbols=TQQQ_SOXL_SYMBOLS,
            ),
            scoring_config=HoldingRuleScoringConfig(
                scoring_id="v652-reversal-frontier-null",
                rule_version="v580-prior-weak-reversal-v1",
                cost_model_id="standard-9bp-v1",
                max_entries_per_session=1,
                max_concurrent_positions=1,
            ),
        )
        results.append(
            {
                "component_candidate_id": record["candidate_id"],
                "definition": record["definition"],
                "passed": result.passed,
                "reason_code": result.reason_code,
                "observed_profit": result.observed_profit,
                "observed_accepted_entries": result.observed_score.accepted_entry_count,
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
        )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version": 652,
        "source_version": 580,
        "candidate_count": len(results),
        "factory_null_passes": sum(item["passed"] for item in results),
        "results": results,
        "elapsed_seconds": time.perf_counter() - started,
    }
    prior.v12._atomic(args.output, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
