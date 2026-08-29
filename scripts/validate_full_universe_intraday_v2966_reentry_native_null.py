"""Family-wise native null for the v2866-v2965 one-reentry overlay."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import evaluate_full_universe_intraday_v2266_v2365_post_entry_risk as base
import evaluate_full_universe_intraday_v2366_v2465_conditional_exit as conditional
import evaluate_full_universe_intraday_v2866_v2965_one_reentry as reentry
import numpy as np

PROPOSAL = Path(__file__).resolve().parents[1] / (
    "research/proposals/full_universe_intraday_v2966_reentry_native_null/proposal.json"
)
CODE_PATH = Path(__file__)
CODE_DEPENDENCIES = (Path(base.__file__), Path(conditional.__file__), Path(reentry.__file__))
EXPECTED_ELIGIBLE = 22


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compound(values: np.ndarray) -> float:
    return float(np.prod(1.0 + values) - 1.0)


def capped_counterfactual(cube, development, record, models, definition):
    base.stopped_raw = conditional.stopped_raw
    streams, _, _ = base.build_streams(cube, development, record, models, definition)
    output = []
    for index, delay in enumerate((0, 0, 1)):
        anchor_selected, _, anchor_active = base.anchor_route(cube, models, delay)
        component_selected, _, component_active = base.component_route(cube, record, delay)
        same = (anchor_selected == component_selected) & anchor_active & component_active
        output.append(base.risk.scaled(streams[index], np.where(same, 0.775, 1.0)))
    return tuple(output)


def candidate_streams(cube, development, record, models, definition):
    base.stopped_raw = reentry.stopped_raw
    return reentry.build_streams(cube, development, record, models, definition)[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    started = time.perf_counter()
    proposal = json.loads(PROPOSAL.read_text())
    source = json.loads(args.source.read_text())
    eligible = [item for item in source["records"] if item["pre_native_overlay_null_pass"]]
    if len(eligible) != EXPECTED_ELIGIBLE:
        raise RuntimeError("PRE_NULL_FAMILY_SIZE_CHANGED")
    frozen = next(
        item for item in eligible if item["candidate_id"] == proposal["frozen_candidate"]
    )
    if source["ranked_candidate_ids"][0] != frozen["candidate_id"]:
        raise RuntimeError("FROZEN_WINNER_CHANGED")
    cube = base.prior.v53.Cube(args.root, "alpaca", 0)
    record = base.component_record()
    models = base.prior.v44._fit(cube, (20, 23, 26, 29), 72)
    mask = cube.masks()["development_all"]
    candidates = []
    for item in eligible:
        definition = item["definition"]
        candidate = candidate_streams(cube, cube, record, models, definition)[0]
        counter = capped_counterfactual(cube, cube, record, models, definition)[0]
        candidate_values = candidate.values[mask]
        counter_values = counter.values[mask]
        delta = candidate_values - counter_values
        candidates.append(
            {
                "candidate_id": item["candidate_id"],
                "counter_values": counter_values,
                "delta": delta,
                "observed_marginal_improvement": compound(candidate_values)
                - compound(counter_values),
            }
        )
    chosen = next(item for item in candidates if item["candidate_id"] == frozen["candidate_id"])
    rng = np.random.default_rng(int(proposal["seed"]))
    repetitions = int(proposal["repetitions"])
    permutation_max, shift_max = [], []
    count = int(mask.sum())
    for _ in range(repetitions):
        permutation = rng.permutation(count)
        shift = int(rng.integers(int(proposal["safe_shift_minimum_sessions"]), count - 4))
        permutation_max.append(
            max(
                compound(item["counter_values"] + item["delta"][permutation])
                - compound(item["counter_values"])
                for item in candidates
            )
        )
        shift_max.append(
            max(
                compound(item["counter_values"] + np.roll(item["delta"], shift))
                - compound(item["counter_values"])
                for item in candidates
            )
        )
    percentile = float(proposal["percentile"])
    permutation_threshold = float(np.quantile(permutation_max, percentile))
    shift_threshold = float(np.quantile(shift_max, percentile))
    observed = float(chosen["observed_marginal_improvement"])
    passed = observed > permutation_threshold and observed > shift_threshold
    evidence = {
        "candidate_id": frozen["candidate_id"],
        "observed": observed,
        "permutation_threshold": permutation_threshold,
        "shift_threshold": shift_threshold,
        "permutation_statistics": permutation_max,
        "shift_statistics": shift_max,
    }
    evidence_sha = hashlib.sha256(
        json.dumps(evidence, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    payload = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "version": proposal["version"],
        "candidate_id": frozen["candidate_id"],
        "eligible_family_size": len(eligible),
        "development_sessions": count,
        "native_overlay_null": {
            "passed": passed,
            "observed_marginal_improvement": observed,
            "session_permutation_maxT_95pct": permutation_threshold,
            "safe_circular_shift_maxT_95pct": shift_threshold,
            "repetitions": repetitions,
            "percentile": percentile,
            "seed": proposal["seed"],
            "evidence_sha256": evidence_sha,
        },
        "cumulative_bonferroni_passed": False,
        "classification": "MILESTONE_INHERITED_EXCEPTION_REVIEW" if passed else "REJECTED_NULL",
        "admitted": False,
        "elapsed_seconds": time.perf_counter() - started,
        "contract": {
            "proposal_sha256": sha(PROPOSAL),
            "code_sha256": sha(CODE_PATH),
            "source_sha256": sha(args.source),
            "dependency_sha256": {path.name: sha(path) for path in CODE_DEPENDENCIES},
        },
    }
    base.prior.v12._atomic(args.output, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
