"""Fail-closed execution-causality audit for the frozen v9292 research graph."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import evaluate_full_universe_intraday_v6695_v6794_state_gated_wide_fill as base

V9292_ID = "lev-v9292-d229bbc0e792bfcf"
LATE_GATE_DECISION = 23
DECLARED_LATE_ENTRY = 24


def routed_parent_ids() -> tuple[str, ...]:
    anchor_ids = (
        base.prior.route.MODERN_PARENT,
        base.prior.route.TRANSFER_PARENT,
        base.prior.cash.FALLBACK_PARENT,
    )
    return tuple(dict.fromkeys((*anchor_ids, *base.FILL_PARENTS)))


def audit(source: dict) -> dict:
    source_map = {item["candidate_id"]: item for item in source["records"]}
    parents = []
    for candidate_id in routed_parent_ids():
        definition = source_map[candidate_id]["definition"]
        strategy = definition["strategy"]
        decision = int(strategy["decision"])
        entry = decision + 1
        parents.append(
            {
                "candidate_id": candidate_id,
                "decision_bar": decision,
                "native_entry_bar": entry,
                "exit_bar": int(strategy["exit"]),
                "enters_before_declared_late_entry": entry < DECLARED_LATE_ENTRY,
            }
        )
    offenders = [item for item in parents if item["enters_before_declared_late_entry"]]
    return {
        "schema_version": "1.0.0",
        "candidate_id": V9292_ID,
        "status": "REJECTED_NONCAUSAL_LATE_ROUTE_REPRICING_PARITY" if offenders else "PASS",
        "late_gate_decision_bar": LATE_GATE_DECISION,
        "declared_late_entry_bar": DECLARED_LATE_ENTRY,
        "routed_parent_count": len(parents),
        "offending_parent_count": len(offenders),
        "offending_parents": offenders,
        "reason": (
            "The bar-23 veto scales full-session parent returns whose native entries occur before bar 24; the research graph does not reprice those parents at bar 24."
            if offenders
            else None
        ),
        "paper_activation_allowed": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = audit(json.loads(args.source.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    if result["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
