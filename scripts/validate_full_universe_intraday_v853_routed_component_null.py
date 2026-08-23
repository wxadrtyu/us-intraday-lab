"""v853 native null for the frozen v798 state-routed component."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import evaluate_full_universe_intraday_v248_v347_mechanism_campaign as prior
import evaluate_full_universe_intraday_v753_v852_dual_component_routing as campaign
import numpy as np
import pandas as pd
import validate_full_universe_intraday_v246_component_factory_null as native

from us_intraday_lab.validation.null_tests import (
    HoldingRuleScoringConfig,
    NullTestConfig,
    run_null_tests,
)
from us_intraday_lab.validation.stability import TQQQ_SOXL_SYMBOLS

def _selected(source_dir: Path, *, first: int, last: int, expected: str) -> dict:
    records = []
    for version in range(first, last + 1):
        payload = json.loads(
            (source_dir / f"full-universe-intraday-v{version}-exact.json").read_text(
                encoding="utf-8"
            )
        )
        records.extend(record for record in payload["records"] if record["pre_factory_null_pass"])
    selected = max(records, key=lambda record: tuple(record["development_rank"]))
    if selected["candidate_id"] != expected:
        raise RuntimeError("V853_FROZEN_SELECTION_MISMATCH")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--component-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--first-version", type=int, default=campaign.FIRST_VERSION)
    parser.add_argument("--last-version", type=int, default=campaign.LAST_VERSION)
    parser.add_argument("--expected", default="lev-v798-d0612cdc630bb224")
    parser.add_argument("--validation-version", type=int, default=853)
    parser.add_argument("--seed", type=int, default=20_260_822)
    args = parser.parse_args()
    started = time.perf_counter()
    selected = _selected(
        args.source_dir,
        first=args.first_version,
        last=args.last_version,
        expected=args.expected,
    )
    definition = selected["definition"]
    cube = prior.v53.Cube(args.root, "alpaca", 0)
    matrix = prior._state_matrix(cube, str(definition["state_clock"]))
    coefficients = definition["state_coefficients"]
    train = cube.masks()["train_2022_2023"]
    means = {name: float(np.nanmean(matrix[name][train])) for name in coefficients}
    scales = {name: max(1e-8, float(np.nanstd(matrix[name][train]))) for name in coefficients}
    score = prior._state_score(matrix, coefficients, means, scales)
    allowed = np.isfinite(score) & (score >= float(definition["state_threshold"]))
    allowed_sessions = {
        pd.Timestamp(cube.sessions[index]).date() for index in np.flatnonzero(allowed)
    }
    component = campaign._component_record(
        args.component_dir, str(definition["v449_component_id"])
    )
    opportunities = tuple(
        item for item in native._opportunities(cube, component) if item.session in allowed_sessions
    )
    result = run_null_tests(
        opportunities,
        config=NullTestConfig(
            seed=args.seed,
            repetitions=200,
            percentile=0.95,
            symbols=TQQQ_SOXL_SYMBOLS,
        ),
        scoring_config=HoldingRuleScoringConfig(
            scoring_id=f"v{args.validation_version}-routed-component-null",
            rule_version=f"{selected['candidate_id']}-routed-v60-component-v1",
            cost_model_id="standard-9bp-v1",
            max_entries_per_session=1,
            max_concurrent_positions=1,
        ),
    )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version": args.validation_version,
        "candidate_id": selected["candidate_id"],
        "component_candidate_id": definition["v449_component_id"],
        "allowed_development_sessions": len(allowed_sessions),
        "routed_component_factory_null": native._result_payload(result),
        "inherited_v45_factory_null_passed": False,
        "cumulative_bonferroni_passed": False,
        "elapsed_seconds": time.perf_counter() - started,
    }
    prior.v12._atomic(args.output, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
