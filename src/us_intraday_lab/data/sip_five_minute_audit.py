"""Fail-closed coverage audit for full-market SIP five-minute bars."""

from __future__ import annotations

from datetime import date
from typing import Any

import exchange_calendars as xcals
import pandas as pd

DECISION_BARS = (2, 5, 11, 17, 23)
HOLDING_BARS = (1, 2, 4, 6)
COVERAGE_FLOOR = 0.95


def _required_bar_numbers() -> tuple[int, ...]:
    required: set[int] = set()
    for decision in DECISION_BARS:
        required.add(decision)
        for entry_delay in (1, 2):
            entry = decision + entry_delay
            required.add(entry)
            required.update(entry + holding for holding in HOLDING_BARS)
    return tuple(sorted(required))


def _session_opens(expected_sessions: tuple[date, ...]) -> dict[date, pd.Timestamp]:
    if not expected_sessions:
        return {}
    calendar = xcals.get_calendar("XNYS")
    sessions = calendar.sessions_in_range(
        pd.Timestamp(min(expected_sessions)), pd.Timestamp(max(expected_sessions))
    )
    expected = set(expected_sessions)
    return {
        session.date(): calendar.session_open(session).tz_convert("UTC")
        for session in sessions
        if session.date() in expected
    }


def audit_sip_five_minute(
    *,
    bars: pd.DataFrame,
    monthly_decisions: pd.DataFrame,
    assets: pd.DataFrame,
    expected_sessions: tuple[date, ...],
    historical_master_validated: bool,
) -> dict[str, Any]:
    """Audit required decision/entry/exit clocks without filling missing bars."""
    reasons: list[str] = []
    required_bar_numbers = _required_bar_numbers()
    required_columns = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
    if not required_columns.issubset(bars.columns):
        missing = sorted(required_columns.difference(bars.columns))
        return {
            "schema_version": "1.0.0",
            "strategy_metrics_permitted": False,
            "rejection_reasons": ["REQUIRED_BAR_COLUMNS_MISSING"],
            "missing_columns": missing,
            "required_clock_coverage_ratio": 0.0,
        }

    normalized = bars.loc[:, sorted(required_columns)].copy()
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True)
    duplicate_rows = int(normalized.duplicated(["symbol", "timestamp"]).sum())
    if duplicate_rows:
        reasons.append("DUPLICATE_SYMBOL_TIMESTAMP")

    invalid_ohlc = (
        (normalized["high"] < normalized[["open", "close", "low"]].max(axis=1))
        | (normalized["low"] > normalized[["open", "close", "high"]].min(axis=1))
        | (normalized[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (normalized["volume"] < 0)
    )
    invalid_ohlc_rows = int(invalid_ohlc.sum())
    if invalid_ohlc_rows:
        reasons.append("INVALID_OHLCV")

    if not historical_master_validated:
        reasons.append("INDEPENDENT_HISTORICAL_MASTER_MISSING")

    if not expected_sessions:
        reasons.append("EXPECTED_XNYS_SESSION_SET_EMPTY")
    opens = _session_opens(expected_sessions)
    missing_calendar_sessions = sorted(set(expected_sessions).difference(opens))
    if missing_calendar_sessions:
        reasons.append("EXPECTED_XNYS_SESSION_NOT_IN_CALENDAR")

    if not {"symbol", "session_date", "eligible"}.issubset(monthly_decisions.columns):
        reasons.append("ELIGIBILITY_DECISION_COLUMNS_MISSING")
        eligible = pd.DataFrame(columns=["symbol", "session_date"])
    else:
        eligible = monthly_decisions.loc[monthly_decisions["eligible"].astype(bool), ["symbol", "session_date"]].copy()
        eligible["session_date"] = pd.to_datetime(eligible["session_date"]).dt.date
        eligible = eligible.loc[eligible["session_date"].isin(expected_sessions)].drop_duplicates()

    asset_symbols = set(assets.get("symbol", pd.Series(dtype=str)).astype(str))
    unknown_symbols = sorted(set(eligible["symbol"].astype(str)).difference(asset_symbols))
    if unknown_symbols:
        reasons.append("ELIGIBLE_SYMBOL_NOT_IN_ASSET_SNAPSHOT")

    expected_keys: set[tuple[str, pd.Timestamp]] = set()
    for row in eligible.itertuples(index=False):
        session = row.session_date
        session_open = opens.get(session)
        if session_open is None:
            continue
        for bar_number in required_bar_numbers:
            expected_keys.add(
                (str(row.symbol), session_open + pd.Timedelta(minutes=5 * bar_number))
            )
    observed_keys = set(
        zip(normalized["symbol"].astype(str), normalized["timestamp"], strict=False)
    )
    observed_required = len(expected_keys.intersection(observed_keys))
    expected_required = len(expected_keys)
    coverage = observed_required / expected_required if expected_required else 0.0
    if expected_required == 0:
        reasons.append("EXPECTED_REQUIRED_CLOCK_SET_EMPTY")
    elif coverage < COVERAGE_FLOOR:
        reasons.append("REQUIRED_CLOCK_COVERAGE_BELOW_95_PERCENT")

    minute = normalized["timestamp"].dt.minute
    off_grid_rows = int((minute.mod(5) != 0).sum())
    if off_grid_rows:
        reasons.append("OFF_FIVE_MINUTE_GRID")

    return {
        "schema_version": "1.0.0",
        "strategy_metrics_permitted": not reasons,
        "rejection_reasons": reasons,
        "expected_sessions": [session.isoformat() for session in expected_sessions],
        "eligible_symbol_sessions": len(eligible),
        "required_clock_count": expected_required,
        "observed_required_clock_count": observed_required,
        "required_clock_coverage_ratio": coverage,
        "duplicate_rows": duplicate_rows,
        "off_grid_rows": off_grid_rows,
        "invalid_ohlcv_rows": invalid_ohlc_rows,
        "unknown_eligible_symbols": unknown_symbols,
        "historical_master_validated": historical_master_validated,
        "missing_data_policy": "preserve_missing_no_fill_no_cash_substitution",
    }
