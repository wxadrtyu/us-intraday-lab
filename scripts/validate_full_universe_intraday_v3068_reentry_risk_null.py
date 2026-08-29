"""Family-wise risk-timing null for the confirmation-selected reentry overlay."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import evaluate_full_universe_intraday_v2266_v2365_post_entry_risk as base
import evaluate_full_universe_intraday_v2866_v2965_one_reentry as reentry
import evaluate_full_universe_intraday_v2967_v3066_reentry_confirmation as confirmation
import numpy as np

PROPOSAL = Path(__file__).resolve().parents[1] / (
    "research/proposals/full_universe_intraday_v3068_reentry_risk_null/proposal.json"
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def max_drawdown(values: np.ndarray) -> float:
    equity = np.cumprod(1.0 + values)
    peak = np.maximum.accumulate(np.r_[1.0, equity])
    path = np.r_[1.0, equity]
    return float(np.max(1.0 - path / peak))


def tail_loss(values: np.ndarray) -> float:
    return base.risk.tail_loss(values)


def risk_statistic(candidate: tuple[np.ndarray, ...], matched: tuple[np.ndarray, ...]) -> float:
    scores = []
    for values, baseline in zip(candidate, matched, strict=True):
        base_mdd, base_tail = max_drawdown(baseline), tail_loss(baseline)
        mdd_reduction = 1.0 - max_drawdown(values) / base_mdd
        tail_reduction = 1.0 - tail_loss(values) / base_tail
        scores.extend((mdd_reduction / 0.20, tail_reduction / 0.15))
    return float(min(scores))


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
    if len(eligible) != 43:
        raise RuntimeError("PRE_NULL_FAMILY_SIZE_CHANGED")
    frozen = next(
        item for item in eligible if item["candidate_id"] == proposal["frozen_candidate"]
    )
    if source["ranked_candidate_ids"][0] != frozen["candidate_id"]:
        raise RuntimeError("FROZEN_WINNER_CHANGED")
    cube = base.prior.v53.Cube(args.root, "alpaca", 0)
    component = base.component_record()
    models = base.prior.v44._fit(cube, (20, 23, 26, 29), 72)
    baseline = tuple(
        base.risk.add(left, right) for left, right in base.risk.baseline_parts(cube, cube)
    )
    oos = cube.masks()["development_oos_2024_2025"]
    candidates = []
    for item in eligible:
        definition = item["definition"]
        reentry.REENTRY_RECOVERY = confirmation.recovery_threshold(
            definition["application_mode"]
        )
        base.stopped_raw = reentry.stopped_raw
        streams, valids, _ = confirmation.build_streams(
            cube, cube, component, models, definition
        )
        candidate_values = tuple(stream.values[oos] for stream in streams)
        matched_values = tuple(
            baseline[index].values[oos] * valids[index][oos]
            for index in range(3)
        )
        candidates.append(
            {
                "candidate_id": item["candidate_id"],
                "matched": matched_values,
                "delta": tuple(
                    values - matched
                    for values, matched in zip(candidate_values, matched_values, strict=True)
                ),
                "observed": risk_statistic(candidate_values, matched_values),
            }
        )
    chosen = next(item for item in candidates if item["candidate_id"] == frozen["candidate_id"])
    rng = np.random.default_rng(int(proposal["seed"]))
    count = int(oos.sum())
    permutation_max, shift_max = [], []
    for _ in range(int(proposal["repetitions"])):
        permutation = rng.permutation(count)
        shift = int(rng.integers(int(proposal["safe_shift_minimum_sessions"]), count - 4))
        permutation_max.append(
            max(
                risk_statistic(
                    tuple(
                        matched + delta[permutation]
                        for matched, delta in zip(item["matched"], item["delta"], strict=True)
                    ),
                    item["matched"],
                )
                for item in candidates
            )
        )
        shift_max.append(
            max(
                risk_statistic(
                    tuple(
                        matched + np.roll(delta, shift)
                        for matched, delta in zip(item["matched"], item["delta"], strict=True)
                    ),
                    item["matched"],
                )
                for item in candidates
            )
        )
    percentile = float(proposal["percentile"])
    permutation_threshold = float(np.quantile(permutation_max, percentile))
    shift_threshold = float(np.quantile(shift_max, percentile))
    observed = float(chosen["observed"])
    passed = observed >= 1.0 and observed > permutation_threshold and observed > shift_threshold
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
        "oos_sessions": count,
        "native_risk_timing_null": {
            "passed": passed,
            "observed_normalized_worst_risk_improvement": observed,
            "session_permutation_maxT_95pct": permutation_threshold,
            "safe_circular_shift_maxT_95pct": shift_threshold,
            "repetitions": proposal["repetitions"],
            "percentile": percentile,
            "seed": proposal["seed"],
            "evidence_sha256": evidence_sha,
        },
        "marginal_profit_null_passed": False,
        "cumulative_bonferroni_passed": False,
        "classification": "RISK_MILESTONE_INHERITED_EXCEPTION_REVIEW" if passed else "REJECTED_RISK_NULL",
        "admitted": False,
        "elapsed_seconds": time.perf_counter() - started,
        "contract": {
            "proposal_sha256": sha(PROPOSAL),
            "code_sha256": sha(Path(__file__)),
            "source_sha256": sha(args.source),
            "dependency_sha256": {
                Path(base.__file__).name: sha(Path(base.__file__)),
                Path(reentry.__file__).name: sha(Path(reentry.__file__)),
                Path(confirmation.__file__).name: sha(Path(confirmation.__file__)),
            },
        },
    }
    base.prior.v12._atomic(args.output, payload)
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
