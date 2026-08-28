"""Fetch one completed Twelve Data session and append v4.1 theoretical evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd

from us_intraday_lab.data.calendar import expected_minute_index
from us_intraday_lab.dual_sleeve import DualSleeveParameters
from us_intraday_lab.research_shadow import ResearchShadowStore
from us_intraday_lab.research_shadow_alpaca import (
    evaluate_alpaca_dual_sleeve_session,
    history_bounds,
)
from us_intraday_lab.research_shadow_twelvedata import TwelveDataHistory


def _json_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _load_selection(proposal: dict[str, object], path: Path) -> dict[str, object]:
    selection = json.loads(path.read_text(encoding="utf-8"))
    selection_hash = selection.pop("selection_sha256")
    if _json_sha256(selection) != selection_hash:
        raise ValueError("v4.1 selection manifest hash mismatch")
    if selection["proposal_sha256"] != _json_sha256(proposal):
        raise ValueError("v4.1 proposal hash mismatch")
    if not selection["all_development_gates_passed"]:
        raise ValueError("v4.1 development gates have not all passed")
    return selection


def _load_or_fetch_bars(
    *,
    cache_dir: Path,
    campaign_id: str,
    session_date: date,
    universe: tuple[str, ...],
    read_only_cache: bool = False,
) -> pd.DataFrame:
    directory = cache_dir / campaign_id
    path = directory / f"{session_date.isoformat()}.parquet"
    if path.exists():
        return pd.read_parquet(path)
    start, end = history_bounds(session_date)
    symbols = (*universe, "SPY")
    bars: pd.DataFrame | None = None
    if directory.exists():
        previous_paths = sorted(
            (
                candidate
                for candidate in directory.glob("????-??-??.parquet")
                if candidate.stem < session_date.isoformat()
            ),
            reverse=True,
        )
        for previous_path in previous_paths:
            previous_date = date.fromisoformat(previous_path.stem)
            previous = pd.read_parquet(previous_path)
            if set(previous["symbol"].unique()) != set(symbols):
                continue
            previous_end = history_bounds(previous_date)[1]
            if previous_end >= end:
                continue
            incremental = TwelveDataHistory.from_environment(requests_per_minute=8.0).fetch(
                symbols=symbols,
                start=previous_end,
                end=end,
            )
            bars = pd.concat((previous, incremental), ignore_index=True)
            bars = bars.drop_duplicates(["symbol", "timestamp"], keep="last")
            timestamps = pd.to_datetime(bars["timestamp"], utc=True)
            bars = bars.loc[(timestamps >= start) & (timestamps < end)].copy()
            bars = bars.sort_values(["timestamp", "symbol"]).reset_index(drop=True)
            break
    if bars is None:
        bars = TwelveDataHistory.from_environment(requests_per_minute=8.0).fetch(
            symbols=symbols,
            start=start,
            end=end,
        )
    if read_only_cache:
        return bars
    directory.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    bars.to_parquet(temporary, index=False)
    temporary.replace(path)
    return bars


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--campaign-id", required=True)
    parser.add_argument("--session-date", required=True, type=date.fromisoformat)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--read-only-cache", action="store_true")
    args = parser.parse_args()
    official_minutes = expected_minute_index(args.session_date)
    if len(official_minutes) != 390:
        raise ValueError("research shadow session must be a full XNYS session")
    safe_after = official_minutes[-1].to_pydatetime().astimezone(UTC) + timedelta(minutes=20)
    if datetime.now(UTC) < safe_after:
        raise RuntimeError("RESEARCH_SHADOW_SESSION_NOT_CLOSED")
    proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
    if proposal.get("proposal_id") != "twelvedata-dual-sleeve-v4-1":
        raise ValueError("unexpected v4.1 proposal")
    forward_data = proposal.get("forward_data_contract", {})
    if not isinstance(forward_data, dict) or forward_data.get("primary_provider") != "twelve_data":
        raise ValueError("v4.1 primary provider contract mismatch")
    selection = _load_selection(proposal, args.selection)
    parameters = selection["winner_parameters"]
    if not isinstance(parameters, dict):
        raise TypeError("v4.1 winner parameters are invalid")
    frozen = DualSleeveParameters(
        float(parameters["stock_excess_floor"]),
        float(parameters["stock_range_floor"]),
        float(parameters["spy_current_floor"]),
        int(parameters["spy_exit_minute"]),  # type: ignore[arg-type]
    )
    universe = tuple(str(value) for value in proposal["universe"])
    bars = _load_or_fetch_bars(
        cache_dir=args.cache_dir,
        campaign_id=args.campaign_id,
        session_date=args.session_date,
        universe=universe,
        read_only_cache=args.read_only_cache,
    )
    observation = evaluate_alpaca_dual_sleeve_session(
        bars,
        session_date=args.session_date,
        universe=universe,
        parameters=frozen,
        round_trip_cost=float(proposal["cost_contract"]["round_trip_cost_1_5x"]),
    )
    store = ResearchShadowStore(args.root.resolve() / "state" / "research_shadow.sqlite3")
    record = observation.as_record(frozen, provider="twelve_data", feed="minute_composite")
    stress = {}
    for name, cost, delay in (
        ("cost_18bp_return", 0.0018, 0),
        ("delay_5min_9bp_return", 0.0009, 5),
    ):
        evaluated = evaluate_alpaca_dual_sleeve_session(
            bars,
            session_date=args.session_date,
            universe=universe,
            parameters=frozen,
            round_trip_cost=cost,
            execution_delay_minutes=delay,
        )
        stress[name] = evaluated.strategy_return
    record["stress_diagnostics"] = {
        "standard_9bp_return": observation.strategy_return,
        **stress,
        "contract": "same frozen signals; entry delayed five minutes; scheduled exit unchanged",
    }
    digest = store.record_observation(
        campaign_id=args.campaign_id,
        session_date=args.session_date,
        observation=record,
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
                "quality": {
                    "target_spy_minutes": observation.target_spy_minutes,
                    "target_minimum_stock_minutes": observation.target_minimum_stock_minutes,
                },
                "signals": {
                    "stock": observation.stock_signal,
                    "stock_symbol": observation.stock_symbol,
                    "spy": observation.spy_signal,
                },
                "strategy_return": observation.strategy_return,
                "stress_diagnostics": record["stress_diagnostics"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
