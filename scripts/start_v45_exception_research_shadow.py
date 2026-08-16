"""Start the explicitly authorized v45 brokerless research shadow."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

from us_intraday_lab.research_shadow import ResearchShadowStore


def _json_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--start-session-not-before", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
    selection_with_hash = json.loads(args.selection.read_text(encoding="utf-8"))
    selection_hash = selection_with_hash.pop("selection_sha256")
    if _json_sha256(selection_with_hash) != selection_hash:
        raise ValueError("v45 exception selection manifest hash mismatch")
    proposal_hash = _json_sha256(proposal)
    if selection_with_hash["proposal_sha256"] != proposal_hash:
        raise ValueError("v45 exception proposal hash does not match selection")
    gates = selection_with_hash["gate_state"]
    authority = selection_with_hash["exception_authority"]
    if selection_with_hash["promotion_status"] != "USER_AUTHORIZED_RESEARCH_SHADOW_EXCEPTION":
        raise ValueError("v45 candidate lacks an explicit research-shadow exception")
    if authority != {
        "actor": "user",
        "date": "2026-08-16",
        "scope": "research-shadow-only",
        "preserve_failed_null_label": True,
    }:
        raise ValueError("v45 exception authority is invalid")
    if not gates["economic_cost_delay_history_folds_passed"]:
        raise ValueError("v45 economic gates are not eligible for the exception")
    if not gates["consumed_2026_above_5pct"]:
        raise ValueError("v45 weak-market diagnostic gate failed")
    if gates["factory_null_passed"] or gates["all_hard_gates_passed"]:
        raise ValueError("v45 failed-null state must remain explicit")
    forward = proposal["forward_contract"]
    if args.start_session_not_before <= date.fromisoformat(forward["must_start_after"]):
        raise ValueError("v45 research shadow must start after all consumed data")
    if proposal["scope"]["order_route"] != "FORBIDDEN":
        raise ValueError("v45 research shadow cannot expose an order route")
    store = ResearchShadowStore(args.root.resolve() / "state" / "research_shadow.sqlite3")
    campaign_id = store.start_campaign(
        proposal_sha256=proposal_hash,
        selection_sha256=selection_hash,
        winner_id=selection_with_hash["winner_id"],
        parameters=selection_with_hash["winner_parameters"],
        start_session_not_before=args.start_session_not_before,
        minimum_sessions=int(forward["minimum_sessions"]),
        created_at=datetime.now(UTC),
    )
    status = store.status(campaign_id)
    print(
        json.dumps(
            {
                "admission": "USER_AUTHORIZED_RESEARCH_SHADOW_EXCEPTION",
                "campaign_id": campaign_id,
                "failed_null_label_preserved": True,
                "forward_gate_eligible": status.forward_gate_eligible,
                "minimum_sessions": status.minimum_sessions,
                "observed_sessions": status.observed_sessions,
                "order_route": status.order_route,
                "start_session_not_before": args.start_session_not_before.isoformat(),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
