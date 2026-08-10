"""Start the v4 prospective research shadow without a broker route."""

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
        raise ValueError("v4 selection manifest hash mismatch")
    proposal_hash = _json_sha256(proposal)
    if selection_with_hash["proposal_sha256"] != proposal_hash:
        raise ValueError("v4 proposal hash does not match selection")
    if not selection_with_hash["all_development_gates_passed"]:
        raise ValueError("v4 development gates have not all passed")
    if selection_with_hash["promotion_status"] != "WAITING_FOR_NEW_FORWARD_INTERVAL":
        raise ValueError("v4 selection is not eligible for research shadow")
    forward = proposal["forward_contract"]
    earliest = date.fromisoformat(forward["must_start_after"])
    if args.start_session_not_before <= earliest:
        raise ValueError("v4 research shadow must start after all consumed final data")
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
                "campaign_id": campaign_id,
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
