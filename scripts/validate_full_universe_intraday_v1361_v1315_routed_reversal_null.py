"""v1361 native null for v1315's stress-routed afternoon reversal sleeve."""

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
import validate_full_universe_intraday_v651_reversal_component_null as reversal_null
import validate_full_universe_intraday_v853_routed_component_null as routed

from us_intraday_lab.validation.null_tests import (
    HoldingRuleScoringConfig,
    NullTestConfig,
    run_null_tests,
)
from us_intraday_lab.validation.stability import TQQQ_SOXL_SYMBOLS


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source-dir", required=True, type=Path)
    parser.add_argument("--component-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    expected = "lev-v1315-b6edb535dc9901a6"
    selected = routed._selected(
        args.source_dir, first=1261, last=1360, expected=expected
    )
    definition = selected["definition"]
    cube = prior.v53.Cube(args.root, "alpaca", 0)
    matrix = prior._state_matrix(cube, str(definition["state_clock"]))
    coefficients = definition["state_coefficients"]
    train = cube.masks()["train_2022_2023"]
    means = {name: float(np.nanmean(matrix[name][train])) for name in coefficients}
    scales = {
        name: max(1e-8, float(np.nanstd(matrix[name][train]))) for name in coefficients
    }
    score = prior._state_score(matrix, coefficients, means, scales)
    allowed = np.isfinite(score) & (score >= float(definition["state_threshold"]))
    allowed_sessions = {
        pd.Timestamp(cube.sessions[index]).date() for index in np.flatnonzero(allowed)
    }
    component = campaign._component_record(
        args.component_dir, str(definition["reversal_component_id"])
    )
    component_selection = {
        "component_definition": component["definition"],
        "component_model": component["model"],
    }
    opportunities = tuple(
        item
        for item in reversal_null._opportunities(cube, component_selection)
        if item.session in allowed_sessions
    )
    result = run_null_tests(
        opportunities,
        config=NullTestConfig(
            seed=20_260_825,
            repetitions=200,
            percentile=0.95,
            symbols=TQQQ_SOXL_SYMBOLS,
        ),
        scoring_config=HoldingRuleScoringConfig(
            scoring_id="v1361-routed-reversal-null",
            rule_version=f"{expected}-routed-v580-reversal-v1",
            cost_model_id="standard-9bp-v1",
            max_entries_per_session=1,
            max_concurrent_positions=1,
        ),
    )
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version": 1361,
        "candidate_id": expected,
        "component_candidate_id": definition["reversal_component_id"],
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
