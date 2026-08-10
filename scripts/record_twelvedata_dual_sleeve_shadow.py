"""Fetch one completed Alpaca IEX session and append v4 theoretical evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from us_intraday_lab.data.calendar import expected_minute_index
from us_intraday_lab.dual_sleeve import DualSleeveParameters
from us_intraday_lab.research_shadow import ResearchShadowStore
from us_intraday_lab.research_shadow_alpaca import (
    AlpacaIexHistory,
    evaluate_alpaca_dual_sleeve_session,
    history_bounds,
)


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
    official_minutes = expected_minute_index(args.session_date)
    if len(official_minutes) != 390:
        raise ValueError("research shadow session must be a full XNYS session")
    safe_after = official_minutes[-1].to_pydatetime().astimezone(UTC) + timedelta(minutes=20)
    if datetime.now(UTC) < safe_after:
        raise RuntimeError("RESEARCH_SHADOW_SESSION_NOT_CLOSED")
    proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
    selection = json.loads(args.selection.read_text(encoding="utf-8"))
    selection_hash = selection.pop("selection_sha256")
    if _json_sha256(selection) != selection_hash:
        raise ValueError("v4 selection manifest hash mismatch")
    if selection["proposal_sha256"] != _json_sha256(proposal):
        raise ValueError("v4 proposal hash mismatch")
    parameters = selection["winner_parameters"]
    frozen = DualSleeveParameters(
        float(parameters["stock_excess_floor"]),
        float(parameters["stock_range_floor"]),
        float(parameters["spy_current_floor"]),
        int(parameters["spy_exit_minute"]),  # type: ignore[arg-type]
    )
    universe = tuple(proposal["universe"])
    start, end = history_bounds(args.session_date)
    bars = AlpacaIexHistory.from_environment().fetch(
        symbols=(*universe, "SPY"), start=start, end=end
    )
    observation = evaluate_alpaca_dual_sleeve_session(
        bars,
        session_date=args.session_date,
        universe=universe,
        parameters=frozen,
        round_trip_cost=float(proposal["cost_contract"]["round_trip_cost_1_5x"]),
    )
    store = ResearchShadowStore(args.root.resolve() / "state" / "research_shadow.sqlite3")
    digest = store.record_observation(
        campaign_id=args.campaign_id,
        session_date=args.session_date,
        observation=observation.as_record(frozen),
        recorded_at=datetime.now(UTC),
    )
    status = store.status(args.campaign_id)
    print(
        json.dumps(
            {
                "campaign_id": args.campaign_id,
                "content_sha256": digest,
                "forward_gate_eligible": status.forward_gate_eligible,
                "observed_sessions": status.observed_sessions,
                "minimum_sessions": status.minimum_sessions,
                "session_date": args.session_date.isoformat(),
                "signals": {
                    "stock": observation.stock_signal,
                    "stock_symbol": observation.stock_symbol,
                    "spy": observation.spy_signal,
                },
                "strategy_return": observation.strategy_return,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
