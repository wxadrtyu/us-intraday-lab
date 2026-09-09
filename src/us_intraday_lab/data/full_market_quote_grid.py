"""Causal full-market SIP quote targets and deterministic quote matching."""

from __future__ import annotations

from datetime import date, timedelta
from typing import cast

import exchange_calendars  # type: ignore[import-untyped]
import numpy as np
import pandas as pd

from us_intraday_lab.data.quote_feature_acquisition import decision_timestamp

_XNYS = exchange_calendars.get_calendar("XNYS")
DEFAULT_DECISION_BARS = (2, 5, 11, 17, 23)
DEFAULT_HOLDING_BARS = (1, 2, 4, 6)


def build_expected_quote_grid(
    *,
    decisions: pd.DataFrame,
    start: date,
    end: date,
    decision_bars: tuple[int, ...] = DEFAULT_DECISION_BARS,
    holding_bars: tuple[int, ...] = DEFAULT_HOLDING_BARS,
) -> pd.DataFrame:
    """Cross each eligible symbol-session with every frozen execution target."""
    if start > end:
        raise ValueError("quote-grid start must not exceed end")
    required = {"month", "symbol", "eligible"}
    missing = sorted(required.difference(decisions.columns))
    if missing:
        raise ValueError(f"monthly decisions missing columns: {missing}")
    if not decision_bars or not holding_bars:
        raise ValueError("decision and holding bars must be non-empty")
    if tuple(sorted(set(decision_bars))) != decision_bars:
        raise ValueError("decision bars must be unique and sorted")
    if tuple(sorted(set(holding_bars))) != holding_bars or holding_bars[0] < 1:
        raise ValueError("holding bars must be positive, unique, and sorted")

    membership = decisions.loc[:, ["month", "symbol", "eligible"]].copy()
    membership["month"] = pd.to_datetime(membership["month"]).dt.date
    membership["symbol"] = membership["symbol"].astype("string").str.upper()
    if membership.duplicated(["month", "symbol"]).any():
        raise ValueError("monthly decisions contain duplicate symbol-month rows")
    membership = membership.loc[membership["eligible"].eq(True)]

    sessions = tuple(
        stamp.date()
        for stamp in _XNYS.sessions_in_range(pd.Timestamp(start), pd.Timestamp(end))
    )
    records: list[dict[str, object]] = []
    for session_date in sessions:
        month = session_date.replace(day=1)
        symbols = tuple(
            sorted(membership.loc[membership["month"].eq(month), "symbol"].astype(str))
        )
        for decision_bar in decision_bars:
            cutoff = decision_timestamp(session_date, decision_bar)
            roles = [
                ("decision_prior", "strictly_prior", cutoff, 0),
                ("entry", "at_or_after", cutoff, 0),
                (
                    "delay_entry_5m",
                    "at_or_after",
                    cutoff + timedelta(minutes=5),
                    1,
                ),
                *[
                    (
                        f"exit_{holding}bar",
                        "at_or_after",
                        cutoff + timedelta(minutes=5 * holding),
                        holding,
                    )
                    for holding in holding_bars
                ],
            ]
            for symbol in symbols:
                for target_role, direction, target, horizon in roles:
                    records.append(
                        {
                            "symbol": symbol,
                            "session_date": session_date,
                            "decision_bar": decision_bar,
                            "target_role": target_role,
                            "horizon_bars": horizon,
                            "target_timestamp": target,
                            "match_direction": direction,
                        }
                    )
    return pd.DataFrame.from_records(records)


def _resolve_direction(
    *, targets: pd.DataFrame, quotes: pd.DataFrame, direction: str, tolerance_seconds: int
) -> pd.DataFrame:
    if targets.empty:
        return targets.copy()
    forward = direction == "at_or_after"
    left = targets.sort_values(["target_timestamp", "symbol"], kind="stable")
    right = quotes.sort_values(["timestamp", "symbol"], kind="stable")
    matched = pd.merge_asof(
        left,
        right,
        by="symbol",
        left_on="target_timestamp",
        right_on="timestamp",
        direction="forward" if forward else "backward",
        allow_exact_matches=forward,
        tolerance=pd.Timedelta(seconds=tolerance_seconds),
    )
    return cast(pd.DataFrame, matched)


def resolve_quote_targets(
    *, targets: pd.DataFrame, quotes: pd.DataFrame, tolerance_seconds: int = 120
) -> pd.DataFrame:
    """Match strictly-prior or at/after SIP quotes without imputing gaps."""
    if tolerance_seconds < 1:
        raise ValueError("quote tolerance must be positive")
    target_required = {"symbol", "target_timestamp", "target_role", "match_direction"}
    quote_required = {
        "symbol",
        "timestamp",
        "bid_price",
        "ask_price",
        "bid_size",
        "ask_size",
    }
    missing_targets = sorted(target_required.difference(targets.columns))
    missing_quotes = sorted(quote_required.difference(quotes.columns))
    if missing_targets:
        raise ValueError(f"quote targets missing columns: {missing_targets}")
    if missing_quotes:
        raise ValueError(f"quotes missing columns: {missing_quotes}")
    directions = set(targets["match_direction"].astype(str))
    if not directions.issubset({"strictly_prior", "at_or_after"}):
        raise ValueError("unknown quote match direction")

    left = targets.copy()
    left["symbol"] = left["symbol"].astype("string").str.upper()
    left["target_timestamp"] = pd.to_datetime(left["target_timestamp"], utc=True)
    left["_target_row"] = np.arange(len(left), dtype=np.int64)
    right = quotes.copy()
    right["symbol"] = right["symbol"].astype("string").str.upper()
    right["timestamp"] = pd.to_datetime(right["timestamp"], utc=True)
    right = right.loc[
        right["bid_price"].gt(0)
        & right["ask_price"].gt(0)
        & right["ask_price"].ge(right["bid_price"])
    ]

    parts = [
        _resolve_direction(
            targets=left.loc[left["match_direction"].eq(direction)],
            quotes=right,
            direction=direction,
            tolerance_seconds=tolerance_seconds,
        )
        for direction in ("strictly_prior", "at_or_after")
    ]
    result = pd.concat(parts, ignore_index=True).sort_values("_target_row", kind="stable")
    result = result.rename(columns={"timestamp": "quote_timestamp"})
    result["quote_available"] = result["quote_timestamp"].notna()
    result["midpoint"] = (result["bid_price"] + result["ask_price"]) / 2.0
    result["relative_spread"] = (
        result["ask_price"] - result["bid_price"]
    ) / result["midpoint"]
    size_sum = result["bid_size"] + result["ask_size"]
    result["size_imbalance"] = np.where(
        size_sum.gt(0), (result["bid_size"] - result["ask_size"]) / size_sum, np.nan
    )
    prior = result["match_direction"].eq("strictly_prior")
    result["quote_age_ms"] = np.where(
        prior,
        (result["target_timestamp"] - result["quote_timestamp"]).dt.total_seconds()
        * 1000.0,
        (result["quote_timestamp"] - result["target_timestamp"]).dt.total_seconds()
        * 1000.0,
    )
    result["locked_or_crossed"] = result["ask_price"].le(result["bid_price"])
    return result.drop(columns="_target_row").reset_index(drop=True)
