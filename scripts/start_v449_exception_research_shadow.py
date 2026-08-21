"""Start the explicitly authorized v449 brokerless research shadow."""

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
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    selection_hash = selection.pop("selection_sha256")
    if _json_sha256(selection) != selection_hash:
        raise ValueError("v449 exception selection manifest hash mismatch")
    proposal_hash = _json_sha256(proposal)
    if selection["proposal_sha256"] != proposal_hash:
        raise ValueError("v449 exception proposal hash does not match selection")
    gates = selection["gate_state"]
    authority = selection["exception_authority"]
    if selection["promotion_status"] != "USER_AUTHORIZED_RESEARCH_SHADOW_EXCEPTION":
        raise ValueError("v449 candidate lacks an explicit research-shadow exception")
    if authority != {
        "actor": "user",
        "date": "2026-08-21",
        "scope": "research-shadow-only",
        "preserve_failed_null_labels": True,
    }:
        raise ValueError("v449 exception authority is invalid")
    required_passes = (
        "economic_cost_delay_history_folds_neighborhood_passed",
        "consumed_2026_above_5pct",
        "component_factory_null_passed",
    )
    if not all(gates[name] for name in required_passes):
        raise ValueError("v449 passed gates are incomplete")
    if (
        gates["inherited_v45_factory_null_passed"]
        or gates["global_bonferroni_passed"]
        or gates["all_hard_gates_passed"]
    ):
        raise ValueError("v449 inherited failed-gate state must remain explicit")
    forward = proposal["forward_contract"]
    if args.start_session_not_before <= date.fromisoformat(forward["must_start_after"]):
        raise ValueError("v449 research shadow must start after authorization")
    if proposal["scope"]["order_route"] != "FORBIDDEN":
        raise ValueError("v449 research shadow cannot expose an order route")
    store = ResearchShadowStore(args.root.resolve() / "state" / "research_shadow.sqlite3")
    campaign_id = store.start_campaign(
        proposal_sha256=proposal_hash,
        selection_sha256=selection_hash,
        winner_id=selection["winner_id"],
        parameters=selection["winner_parameters"],
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
                "component_factory_null_passed": True,
                "failed_anchor_and_bonferroni_labels_preserved": True,
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
