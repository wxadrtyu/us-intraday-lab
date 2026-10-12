"""Frozen full-market long-horizon daily technical multifactor contract."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

FAMILIES = (
    "residual_momentum",
    "trend_quality",
    "low_vol_trend",
    "liquidity_confirmed_breakout",
    "trend_conditioned_reversal",
)
REBALANCE_SESSIONS = (5, 10, 20, 21)
HOLDING_SESSIONS = (5, 10, 20, 42)
TOP_COUNTS = (10, 20, 40, 80, 120)

_DAILY_COLUMNS = {
    "symbol",
    "session_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
    "trade_count",
}
_UNIVERSE_COLUMNS = {"symbol", "month", "information_cutoff", "eligible"}


@dataclass(frozen=True, slots=True)
class Specification:
    family: str
    rebalance_sessions: int
    holding_sessions: int
    top_count: int


def specifications() -> tuple[Specification, ...]:
    """Return the immutable 400-cell discovery grid."""
    result = tuple(
        Specification(family, rebalance, holding, top_count)
        for family in FAMILIES
        for rebalance in REBALANCE_SESSIONS
        for holding in HOLDING_SESSIONS
        for top_count in TOP_COUNTS
    )
    if len(result) != 400 or len(set(result)) != 400:
        raise AssertionError("FULL_MARKET_DAILY_GRID_INVALID")
    return result


def _month_start(values: pd.Series) -> pd.Series:
    timestamps = pd.to_datetime(values, errors="raise")
    return timestamps.dt.to_period("M").dt.to_timestamp()


def validate_monthly_universe(universe: pd.DataFrame) -> pd.DataFrame:
    """Validate one causal point-in-time decision for every symbol-month."""
    missing = _UNIVERSE_COLUMNS.difference(universe.columns)
    if missing:
        raise ValueError(f"FULL_MARKET_DAILY_UNIVERSE_SCHEMA_MISSING:{sorted(missing)}")
    result = universe.copy()
    result["symbol"] = result["symbol"].astype(str).str.upper()
    if result["symbol"].eq("").any():
        raise ValueError("FULL_MARKET_DAILY_UNIVERSE_SYMBOL_INVALID")
    parsed_month = pd.to_datetime(result["month"], errors="raise")
    result["month"] = _month_start(result["month"])
    if not parsed_month.eq(result["month"]).all():
        raise ValueError("FULL_MARKET_DAILY_UNIVERSE_MONTH_NOT_FIRST")
    result["information_cutoff"] = pd.to_datetime(
        result["information_cutoff"], errors="raise"
    ).dt.normalize()
    if result[["symbol", "month"]].duplicated().any():
        raise ValueError("FULL_MARKET_DAILY_UNIVERSE_KEY_DUPLICATE")
    if result["information_cutoff"].ge(result["month"]).any():
        raise ValueError("FULL_MARKET_DAILY_UNIVERSE_CUTOFF_NOT_PRIOR")
    if not result["eligible"].map(lambda value: isinstance(value, (bool, np.bool_))).all():
        raise ValueError("FULL_MARKET_DAILY_UNIVERSE_ELIGIBLE_NOT_BOOLEAN")
    return result.sort_values(["month", "symbol"], kind="stable", ignore_index=True)


def _validate_daily_bars(daily_bars: pd.DataFrame) -> pd.DataFrame:
    missing = _DAILY_COLUMNS.difference(daily_bars.columns)
    if missing:
        raise ValueError(f"FULL_MARKET_DAILY_SCHEMA_MISSING:{sorted(missing)}")
    extras = set(daily_bars.columns).difference(_DAILY_COLUMNS)
    if extras:
        raise ValueError(f"FULL_MARKET_DAILY_FORBIDDEN_INPUT_COLUMN:{sorted(extras)}")
    result = daily_bars.copy()
    result["symbol"] = result["symbol"].astype(str).str.upper()
    result["session_date"] = pd.to_datetime(
        result["session_date"], errors="raise"
    ).dt.normalize()
    if result[["symbol", "session_date"]].duplicated().any():
        raise ValueError("FULL_MARKET_DAILY_KEY_DUPLICATE")
    numeric = ["open", "high", "low", "close", "volume", "vwap", "trade_count"]
    for column in numeric:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    finite = np.isfinite(result[numeric]).all(axis=1)
    positive = result[["open", "high", "low", "close", "vwap"]].gt(0).all(axis=1)
    nonnegative = result[["volume", "trade_count"]].ge(0).all(axis=1)
    if not finite.all() or not positive.all() or not nonnegative.all():
        raise ValueError("FULL_MARKET_DAILY_VALUES_INVALID")
    return result.sort_values(["session_date", "symbol"], kind="stable", ignore_index=True)


def attach_point_in_time_eligibility(
    daily_bars: pd.DataFrame, universe: pd.DataFrame
) -> pd.DataFrame:
    """Attach only the same-month frozen decision and return eligible rows.

    A missing symbol-month decision is a source-contract failure, not an
    opportunity to infer membership or silently remove a bar.
    """
    bars = _validate_daily_bars(daily_bars)
    decisions = validate_monthly_universe(universe)
    bars["universe_month"] = _month_start(bars["session_date"])
    membership = decisions.loc[
        :, ["symbol", "month", "information_cutoff", "eligible"]
    ].rename(columns={"month": "universe_month"})
    attached = bars.merge(
        membership,
        on=["symbol", "universe_month"],
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    if attached["_merge"].ne("both").any():
        raise ValueError("FULL_MARKET_DAILY_UNIVERSE_DECISION_MISSING")
    attached = attached.drop(columns="_merge")
    return attached.loc[attached["eligible"]].sort_values(
        ["session_date", "symbol"], kind="stable", ignore_index=True
    )
