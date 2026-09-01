"""v9103 architecture-native maxT null for the preregistered dual soft-veto merge."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v9098_v9102_dual_soft_veto_merge as merge
import numpy as np

VALIDATION_VERSION = 9103
REPETITIONS = 500
PERCENTILE = 0.95
SEED = 20260901
SAFE_SHIFT_MINIMUM = 20


def _compound(values):
    return float(np.prod(1.0 + values) - 1.0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--parents", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    if selection.get("status") != "COMPLETE" or selection.get("version_range") != [9098, 9102]:
        raise RuntimeError("V9103_SELECTION_NOT_FROZEN_COMPLETE")
    eligible = [item for item in selection["records"] if item["strict_pre_factory_null_pass"]]
    if len(eligible) != 5:
        raise RuntimeError("V9103_ELIGIBLE_CANDIDATE_COUNT_CHANGED")
    development, _, dev_route, _, dev_exp, _ = merge._context(
        args.root, args.source, args.parents
    )
    index = np.flatnonzero(development.masks()["development_all"])
    route_values = dev_route[0].values[index]
    exposures = []
    for item in eligible:
        weight = float(item["definition"]["unstable_reclaim_weight"])
        exposure = merge._blend_exposure(
            dev_exp[merge.UNSTABLE_ID], dev_exp[merge.ABSORPTION_ID], weight
        )
        exposures.append(exposure[index])
    observed = [_compound(route_values * exposure) for exposure in exposures]
    rng = np.random.default_rng(SEED)
    permutation_max, shift_max = [], []
    for _ in range(REPETITIONS):
        permutation_max.append(
            max(
                _compound(route_values * exposure[rng.permutation(len(index))])
                for exposure in exposures
            )
        )
        shift_max.append(
            max(
                _compound(
                    route_values
                    * np.roll(
                        exposure,
                        int(rng.integers(SAFE_SHIFT_MINIMUM, len(index) - 4)),
                    )
                )
                for exposure in exposures
            )
        )
    permutation_threshold = float(np.quantile(permutation_max, PERCENTILE))
    shift_threshold = float(np.quantile(shift_max, PERCENTILE))
    records = []
    for item, profit in zip(eligible, observed, strict=True):
        passed = profit > permutation_threshold and profit > shift_threshold
        records.append(
            {
                "candidate_id": item["candidate_id"],
                "preregistered_primary": item["definition"]["preregistered_primary"],
                "observed_profit": profit,
                "session_signal_permutation_maxT_95pct": permutation_threshold,
                "safe_circular_shift_maxT_95pct": shift_threshold,
                "passed": passed,
            }
        )
    primary = next(item for item in records if item["preregistered_primary"])
    evidence = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "validation_version": VALIDATION_VERSION,
        "candidate_count": len(records),
        "repetitions": REPETITIONS,
        "percentile": PERCENTILE,
        "seed": SEED,
        "native_factory_null_passes": sum(item["passed"] for item in records),
        "preregistered_primary_candidate": primary["candidate_id"],
        "preregistered_primary_passed": primary["passed"],
        "records": records,
    }
    evidence["evidence_sha256"] = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    v34.v12._atomic(args.output, evidence)
    print(
        json.dumps(
            {
                key: evidence[key]
                for key in (
                    "status",
                    "candidate_count",
                    "native_factory_null_passes",
                    "preregistered_primary_candidate",
                    "preregistered_primary_passed",
                    "evidence_sha256",
                )
            }
        )
    )


if __name__ == "__main__":
    main()
