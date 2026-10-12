"""Fail-closed point-in-time path coverage audit for SIP one-minute bars."""

from __future__ import annotations

from datetime import date

import exchange_calendars as xcals  # type: ignore[import-untyped]
import pandas as pd


def audit_one_minute_paths(
    *,
    bars: pd.DataFrame,
    decisions: pd.DataFrame,
    session: date,
    start_minute: int,
    path_minutes: int,
    source_complete: bool,
    coverage_floor: float = 0.95,
) -> dict[str, object]:
    """Count exact symbol-minute paths; a partial source can never clear the gate."""
    if not 0 <= start_minute or path_minutes < 1 or not 0 < coverage_floor <= 1:
        raise ValueError("invalid one-minute path audit bounds")
    if not {"symbol", "timestamp"}.issubset(bars.columns):
        raise ValueError("one-minute bars require symbol and timestamp")
    if not {"symbol", "month", "eligible"}.issubset(decisions.columns):
        raise ValueError("point-in-time decisions require symbol, month, eligible")
    calendar = xcals.get_calendar("XNYS")
    if not calendar.is_session(pd.Timestamp(session)):
        raise ValueError("audit date is not an XNYS session")
    opening = calendar.session_open(pd.Timestamp(session))
    closing = calendar.session_close(pd.Timestamp(session))
    session_minutes = int((closing - opening).total_seconds() // 60)
    if start_minute + path_minutes > session_minutes:
        raise ValueError("path extends beyond actual regular session")

    month = date(session.year, session.month, 1)
    monthly = pd.to_datetime(decisions["month"]).dt.date
    eligible = set(
        decisions.loc[monthly.eq(month) & decisions["eligible"].astype(bool), "symbol"].astype(str)
    )
    timestamps = pd.to_datetime(bars["timestamp"], utc=True, errors="raise")
    duplicate_rows = int(
        bars.assign(timestamp=timestamps).duplicated(["symbol", "timestamp"]).sum()
    )
    actual = set(zip(bars["symbol"].astype(str), timestamps, strict=False))
    required_times = tuple(
        opening + pd.Timedelta(minutes=start_minute + minute) for minute in range(path_minutes)
    )
    observed = sum(
        (symbol, timestamp) in actual for symbol in eligible for timestamp in required_times
    )
    complete = sum(
        all((symbol, timestamp) in actual for timestamp in required_times) for symbol in eligible
    )
    expected = len(eligible) * path_minutes
    path_ratio = complete / len(eligible) if eligible else 0.0
    minute_ratio = observed / expected if expected else 0.0
    reasons: list[str] = []
    if not source_complete:
        reasons.append("INCOMPLETE_SOURCE_GRID")
    if duplicate_rows:
        reasons.append("DUPLICATE_SYMBOL_MINUTE")
    if not eligible:
        reasons.append("NO_POINT_IN_TIME_ELIGIBLE_SYMBOLS")
    elif path_ratio < coverage_floor:
        reasons.append("COMPLETE_PATH_COVERAGE_BELOW_FLOOR")
    return {
        "session": session.isoformat(),
        "month": month.isoformat(),
        "start_minute": start_minute,
        "path_minutes": path_minutes,
        "eligible_symbols": len(eligible),
        "expected_required_minutes": expected,
        "observed_required_minutes": observed,
        "required_minute_ratio": minute_ratio,
        "complete_paths": complete,
        "complete_path_ratio": path_ratio,
        "duplicate_rows": duplicate_rows,
        "source_complete": source_complete,
        "strategy_metrics_permitted": not reasons,
        "rejection_reasons": reasons,
    }
