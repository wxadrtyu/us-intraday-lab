"""Append one completed v247 prospective observation without any broker route."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from us_intraday_lab.data.calendar import expected_minute_index
from us_intraday_lab.research_shadow import ResearchShadowStore
from us_intraday_lab.research_shadow_alpaca import AlpacaIexHistory
from us_intraday_lab.v45_research_shadow import SYMBOLS
from us_intraday_lab.v247_research_shadow import evaluate_v247_shadow_session


def _json_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--session-date", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    official = expected_minute_index(args.session_date)
    if len(official) != 390:
        raise ValueError("v247 shadow session must be a full XNYS session")
    safe_after = official[-1].to_pydatetime().astimezone(UTC) + timedelta(minutes=20)
    if datetime.now(UTC) < safe_after:
        raise RuntimeError("V247_RESEARCH_SHADOW_SESSION_NOT_CLOSED")
    proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    selection_hash = selection.pop("selection_sha256")
    if _json_sha256(selection) != selection_hash:
        raise ValueError("v247 selection hash mismatch")
    if selection["proposal_sha256"] != _json_sha256(proposal):
        raise ValueError("v247 proposal hash mismatch")
    if selection["promotion_status"] != "USER_AUTHORIZED_RESEARCH_SHADOW_EXCEPTION":
        raise ValueError("v247 observation lacks the explicit exception")
    eastern = ZoneInfo("America/New_York")
    start = datetime.combine(args.session_date - timedelta(days=100), time(), eastern)
    end = datetime.combine(args.session_date + timedelta(days=1), time(), eastern)
    bars = AlpacaIexHistory.from_environment().fetch(
        symbols=SYMBOLS,
        start=start.astimezone(UTC),
        end=end.astimezone(UTC),
    )
    observation = evaluate_v247_shadow_session(bars, session_date=args.session_date)
    store = ResearchShadowStore(args.root.resolve() / "state" / "research_shadow.sqlite3")
    digest = store.record_observation(
        campaign_id=args.campaign_id,
        session_date=args.session_date,
        observation=observation.as_record(),
        recorded_at=datetime.now(UTC),
    )
    status = store.status(args.campaign_id)
    print(
        json.dumps(
            {
                "campaign_id": args.campaign_id,
                "content_sha256": digest,
                "forward_gate_eligible": status.forward_gate_eligible,
                "minimum_sessions": status.minimum_sessions,
                "observed_sessions": status.observed_sessions,
                "order_route": status.order_route,
                "session_date": args.session_date.isoformat(),
                "anchor_symbol": observation.anchor.selected_symbol,
                "component_symbol": observation.component_selected_symbol,
                "standard_return": observation.standard_return,
                "cost_18bp_return": observation.cost_18bp_return,
                "delay_5min_return": observation.delay_5min_return,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
