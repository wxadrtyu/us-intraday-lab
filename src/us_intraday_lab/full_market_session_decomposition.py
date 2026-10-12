"""Frozen full-market daily overnight/intraday decomposition contract."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

FAMILIES = (
    "persistent_overnight_drift",
    "overnight_underreaction",
    "persistent_intraday_drift",
    "gap_reversal_quality",
    "session_divergence",
)
LOOKBACKS = (20, 42, 63, 126)
REFRESH_LIFE_PAIRS = ((1, 1), (5, 5), (5, 10), (10, 10), (21, 21))
TOP_COUNTS = (10, 20, 40, 80)

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


@dataclass(frozen=True, slots=True)
class Specification:
    family: str
    lookback: int
    refresh_sessions: int
    life_sessions: int
    top_count: int


def specifications() -> tuple[Specification, ...]:
    """Return the immutable 400-cell session-decomposition grid."""
    result = tuple(
        Specification(family, lookback, refresh, life, top_count)
        for family in FAMILIES
        for lookback in LOOKBACKS
        for refresh, life in REFRESH_LIFE_PAIRS
        for top_count in TOP_COUNTS
    )
    if len(result) != 400 or len(set(result)) != 400:
        raise AssertionError("FULL_MARKET_SESSION_GRID_INVALID")
    return result


def _validate_daily_bars(daily_bars: pd.DataFrame) -> pd.DataFrame:
    missing = _DAILY_COLUMNS.difference(daily_bars.columns)
    if missing:
        raise ValueError(f"SESSION_DAILY_SCHEMA_MISSING:{sorted(missing)}")
    forbidden_tokens = (
        "headline",
        "news",
        "event",
        "filing",
        "sec_",
        "fundamental",
        "issuer",
        "announcement",
    )
    forbidden = sorted(
        column
        for column in daily_bars.columns
        if column not in _DAILY_COLUMNS
        and any(token in column.lower() for token in forbidden_tokens)
    )
    if forbidden:
        raise ValueError(f"FORBIDDEN_INPUT_COLUMN:{forbidden}")
    result = daily_bars.loc[:, sorted(_DAILY_COLUMNS)].copy()
    result["symbol"] = result["symbol"].astype(str).str.upper()
    result["session_date"] = pd.to_datetime(result["session_date"], errors="raise")
    if result.duplicated(["symbol", "session_date"]).any():
        raise ValueError("SESSION_DAILY_KEY_DUPLICATE")
    numeric = ["open", "high", "low", "close", "volume", "vwap", "trade_count"]
    result[numeric] = result[numeric].apply(pd.to_numeric, errors="coerce")
    sentinel = (
        result["volume"].eq(0)
        & result["trade_count"].eq(0)
        & result["vwap"].eq(0)
    )
    result.loc[sentinel, "vwap"] = np.nan
    prices_valid = result[["open", "high", "low", "close"]].gt(0).all(axis=1)
    flows_valid = result[["volume", "trade_count"]].ge(0).all(axis=1)
    vwap_valid = result["vwap"].gt(0) | result["vwap"].isna()
    finite_required = np.isfinite(
        result[["open", "high", "low", "close", "volume", "trade_count"]]
    ).all(axis=1)
    if not (prices_valid & flows_valid & vwap_valid & finite_required).all():
        raise ValueError("SESSION_DAILY_VALUES_INVALID")
    return result.sort_values(["symbol", "session_date"], kind="stable").reset_index(
        drop=True
    )


def build_session_features(daily_bars: pd.DataFrame) -> pd.DataFrame:
    """Build atomic close-to-open and open-to-close features causally."""
    result = _validate_daily_bars(daily_bars)
    grouped = result.groupby("symbol", sort=False, observed=True)
    prior_close = grouped["close"].shift(1)
    result["overnight_log_return"] = np.log(result["open"] / prior_close)
    result["intraday_log_return"] = np.log(result["close"] / result["open"])
    result["close_above_vwap"] = np.where(
        result["vwap"].notna(), result["close"].gt(result["vwap"]).astype(float), np.nan
    )
    result["dollar_volume"] = result["close"] * result["volume"]
    return result


def _rolling(
    frame: pd.DataFrame,
    column: str,
    lookback: int,
    operation: str,
) -> pd.Series:
    grouped = frame.groupby("symbol", sort=False, observed=True)[column]
    if operation == "sum":
        return grouped.transform(
            lambda values: values.rolling(lookback, min_periods=lookback).sum()
        )
    if operation == "mean":
        return grouped.transform(
            lambda values: values.rolling(lookback, min_periods=lookback).mean()
        )
    if operation == "std":
        return grouped.transform(
            lambda values: values.rolling(lookback, min_periods=lookback).std(ddof=1)
        )
    raise ValueError(f"SESSION_ROLLING_OPERATION_INVALID:{operation}")


def _session_rank(frame: pd.DataFrame, values: pd.Series) -> pd.Series:
    ranked = pd.Series(np.nan, index=frame.index, dtype=float)
    for positions in frame.groupby(
        "session_date", sort=False, observed=True
    ).groups.values():
        positions = list(positions)
        session_values = values.loc[positions]
        finite = session_values[np.isfinite(session_values)]
        if finite.empty:
            continue
        lower = finite.quantile(0.01)
        upper = finite.quantile(0.99)
        ordered = frame.loc[finite.index, "symbol"].sort_values(kind="stable").index
        clipped = session_values.loc[ordered].clip(lower=lower, upper=upper)
        ranked.loc[ordered] = clipped.rank(method="first", pct=True).to_numpy()
    return ranked


def score_session_families(features: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Score the five frozen session-decomposition families."""
    if lookback not in LOOKBACKS:
        raise ValueError("SESSION_LOOKBACK_INVALID")
    frame = features.sort_values(["symbol", "session_date"], kind="stable").reset_index(
        drop=True
    )
    overnight_sum = _rolling(frame, "overnight_log_return", lookback, "sum")
    intraday_sum = _rolling(frame, "intraday_log_return", lookback, "sum")
    overnight_hit = _rolling(
        frame.assign(_overnight_hit=frame["overnight_log_return"].gt(0).astype(float)),
        "_overnight_hit",
        lookback,
        "mean",
    )
    intraday_hit = _rolling(
        frame.assign(_intraday_hit=frame["intraday_log_return"].gt(0).astype(float)),
        "_intraday_hit",
        lookback,
        "mean",
    )
    overnight_vol = _rolling(frame, "overnight_log_return", lookback, "std")
    intraday_vol = _rolling(frame, "intraday_log_return", lookback, "std")
    dollar_volume = _rolling(frame, "dollar_volume", lookback, "mean")
    vwap_frequency = _rolling(frame, "close_above_vwap", lookback, "mean")

    ranks = {
        "overnight_sum": _session_rank(frame, overnight_sum),
        "intraday_sum": _session_rank(frame, intraday_sum),
        "overnight_hit": _session_rank(frame, overnight_hit),
        "intraday_hit": _session_rank(frame, intraday_hit),
        "overnight_vol": _session_rank(frame, overnight_vol),
        "intraday_vol": _session_rank(frame, intraday_vol),
        "dollar_volume": _session_rank(frame, dollar_volume),
        "gap_reversal": _session_rank(frame, -frame["overnight_log_return"]),
        "divergence": _session_rank(frame, overnight_sum - intraday_sum),
        "vwap_frequency": _session_rank(frame, vwap_frequency),
    }
    result = frame.loc[:, ["symbol", "session_date"]].copy()
    result["persistent_overnight_drift"] = (
        ranks["overnight_sum"] + ranks["overnight_hit"] + (1.0 - ranks["overnight_vol"])
    ) / 3.0
    result["overnight_underreaction"] = (
        ranks["overnight_sum"] + (1.0 - ranks["intraday_sum"]) + ranks["dollar_volume"]
    ) / 3.0
    result["persistent_intraday_drift"] = (
        ranks["intraday_sum"] + ranks["intraday_hit"] + (1.0 - ranks["intraday_vol"])
    ) / 3.0
    result["gap_reversal_quality"] = (
        ranks["gap_reversal"] + ranks["intraday_sum"] + (1.0 - ranks["overnight_vol"])
    ) / 3.0
    result["session_divergence"] = (
        ranks["divergence"] + ranks["vwap_frequency"] + ranks["dollar_volume"]
    ) / 3.0
    return result
