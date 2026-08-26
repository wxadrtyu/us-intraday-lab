"""Falsify risk improvements attributable to unmatched source availability."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import evaluate_full_universe_intraday_v1865_v1964_risk_overlay as risk
import numpy as np

PROPOSAL = (
    Path(__file__).resolve().parents[1]
    / "research/proposals/validation_v1965_common_availability/proposal.json"
)


def paired_risk(original, candidate, valid, mask):
    common = risk.scaled(original, valid.astype(float))
    base = risk.metrics(common.values[mask], common.benchmark[mask], common.active[mask])
    optimized = risk.metrics(
        candidate.values[mask], candidate.benchmark[mask], candidate.active[mask]
    )
    tail = risk.tail_loss(common.values[mask])
    mdd_reduction = (
        1 - optimized["max_drawdown"] / base["max_drawdown"] if base["max_drawdown"] > 0 else 0.0
    )
    tail_reduction = 1 - risk.tail_loss(candidate.values[mask]) / tail if tail > 0 else 0.0
    return {
        "common_availability_baseline": base,
        "candidate": optimized,
        "mdd_reduction": mdd_reduction,
        "tail_loss_reduction": tail_reduction,
        "passed": mdd_reduction >= 0.2 and tail_reduction >= 0.15,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.perf_counter()
    proposal = json.loads(PROPOSAL.read_text())
    summary = json.loads((args.source_dir / "summary.json").read_text())
    if summary["contract_id"] != proposal["source_contract_id"] or summary["status"] != "COMPLETE":
        raise RuntimeError("SOURCE_IDENTITY_MISMATCH")
    all_records = [
        r
        for path in args.source_dir.glob("full-universe-intraday-v*-exact.json")
        for r in json.loads(path.read_text())["records"]
    ]
    selected = {r["candidate_id"]: r for r in all_records if r["pre_native_overlay_null_pass"]}
    if set(selected) != set(proposal["frozen_candidates"]):
        raise RuntimeError("FROZEN_CANDIDATE_SET_MISMATCH")
    cube = risk.prior.v53.Cube(args.root, "alpaca", 0)
    parts = risk.baseline_parts(cube, cube)
    baseline = tuple(risk.add(a, c) for a, c in parts)
    lagged = risk.prior_loss_mask(baseline[0].values)
    mask = cube.masks()["development_oos_2024_2025"]
    results = []
    for identity in proposal["frozen_candidates"]:
        candidate = selected[identity]
        d = candidate["definition"]
        m = candidate["model"]
        score = risk.prior._state_score(
            risk.prior._state_matrix(cube, d["clock"]), d["coefficients"], m["mean"], m["scale"]
        )
        valid = np.isfinite(score)
        allowed = valid & (score >= d["state_threshold"])
        streams = risk.overlay(parts, allowed, d["policy"], d["gross_budget_cap"], lagged, valid)
        scenarios = {
            name: paired_risk(a, b, valid, mask)
            for name, a, b in zip(risk.NAMES, baseline, streams, strict=True)
        }
        original_obs = risk.observations(cube, streams, True)
        for name, obs in zip(risk.NAMES, original_obs, strict=True):
            for period in (
                "train_2022_2023",
                "2024",
                "2025",
                "development_oos_2024_2025",
                "consumed_2026q1",
                "consumed_2026_all",
            ):
                for metric in (
                    "annualized_return",
                    "max_drawdown",
                    "information_ratio",
                    "total_return",
                ):
                    np.testing.assert_allclose(
                        obs[period][metric], candidate[name][period][metric], rtol=1e-10, atol=1e-10
                    )
        delta = streams[0].values - baseline[0].values
        dev = cube.masks()["development_all"]
        positive = np.flatnonzero(dev & (delta > 1e-12))
        ordered = sorted(positive, key=lambda i: delta[i], reverse=True)
        positive_sum = float(np.maximum(delta[dev], 0).sum())
        results.append(
            {
                "candidate_id": identity,
                "replay_parity_passed": True,
                "scenarios": scenarios,
                "paired_risk_passed": all(s["passed"] for s in scenarios.values()),
                "changed_sessions": {
                    n: int(((np.abs(delta) > 1e-12) & v).sum()) for n, v in cube.masks().items()
                },
                "nonfinite_state_sessions": {
                    n: int((~valid & v).sum()) for n, v in cube.masks().items()
                },
                "top_improvements": [
                    {
                        "date": str(cube.sessions[i]),
                        "baseline_return": float(baseline[0].values[i]),
                        "candidate_return": float(streams[0].values[i]),
                        "delta": float(delta[i]),
                        "state_missing": bool(not valid[i]),
                    }
                    for i in ordered[:5]
                ],
                "largest_positive_delta_share": float(delta[ordered[0]] / positive_sum)
                if ordered
                else 0.0,
                "native_null_status": "PENDING"
                if all(s["passed"] for s in scenarios.values())
                else "NOT_RUN_PAIRED_RISK_FAILED",
                "admitted": False,
            }
        )
    payload = {
        "status": "COMPLETE",
        "validation_version": 1965,
        "proposal_sha256": risk.shared._sha(PROPOSAL),
        "script_sha256": risk.shared._sha(Path(__file__)),
        "source_contract_id": summary["contract_id"],
        "frozen_candidates": len(results),
        "paired_risk_passed": sum(r["paired_risk_passed"] for r in results),
        "admitted": 0,
        "results": results,
        "elapsed_seconds": time.perf_counter() - started,
    }
    risk.prior.v12._atomic(args.output, payload)
    print(json.dumps({k: v for k, v in payload.items() if k != "results"}))


if __name__ == "__main__":
    main()
