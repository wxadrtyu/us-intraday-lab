"""Causal feature computation at completed-bar boundaries."""

from __future__ import annotations

from datetime import date, datetime
from typing import cast

import numpy as np
import pandas as pd

from us_intraday_lab.data.calendar import expected_minute_index
from us_intraday_lab.data.canonicalize import require_finite_canonical_numeric_columns

FEATURE_SET_VERSION = "15m-v1.0.0"
FEATURE_COLUMNS = (
    "symbol",
    "session_date",
    "bar_start",
    "available_at",
    "feature_set_version",
    "return_1",
    "return_3",
    "ema_spread",
    "rsi",
    "atr_bps",
    "volume_ratio",
    "vwap_distance_bps",
    "range_position",
    "minutes_from_open",
)
_REQUIRED_BAR_COLUMNS = frozenset(
    {"symbol", "session_date", "available_at", "open", "high", "low", "close", "volume"}
)
_BAR_SIZE = pd.Timedelta(minutes=15)


def _aware_utc_series(values: pd.Series, *, field_name: str) -> pd.Series:
    timestamps: list[pd.Timestamp] = []
    for value in values:
        timestamp = pd.Timestamp(cast(str | int | float | date | datetime, value))
        if timestamp.tzinfo is None:
            raise ValueError(f"{field_name} must be timezone-aware")
        timestamps.append(timestamp.tz_convert("UTC"))
    return pd.Series(timestamps, index=values.index, dtype="datetime64[ns, UTC]")


def _session_date(value: object) -> date:
    if isinstance(value, datetime) or not isinstance(value, date):
        raise TypeError("session_date must contain date values")
    return value


def _compute_group(group: pd.DataFrame, *, session_date: date) -> pd.DataFrame:
    frame = group.sort_values("available_at", kind="stable").copy()
    close = frame["close"].astype("float64")
    high = frame["high"].astype("float64")
    low = frame["low"].astype("float64")
    volume = frame["volume"].astype("float64")

    frame["bar_start"] = frame["available_at"] - _BAR_SIZE
    frame["feature_set_version"] = FEATURE_SET_VERSION
    frame["return_1"] = close.pct_change(periods=1, fill_method=None)
    frame["return_3"] = close.pct_change(periods=3, fill_method=None)

    fast_ema = close.ewm(span=3, adjust=False, min_periods=3).mean()
    slow_ema = close.ewm(span=8, adjust=False, min_periods=8).mean()
    frame["ema_spread"] = (fast_ema / slow_ema) - 1.0

    change = close.diff()
    average_gain = change.clip(lower=0).rolling(window=14, min_periods=14).mean()
    average_loss = (-change.clip(upper=0)).rolling(window=14, min_periods=14).mean()
    relative_strength = average_gain / average_loss.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + relative_strength))
    rsi = rsi.mask((average_gain == 0.0) & (average_loss == 0.0), 50.0)
    rsi = rsi.mask((average_gain > 0.0) & (average_loss == 0.0), 100.0)
    frame["rsi"] = rsi

    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            high - low,
            (high - previous_close).abs(),
            (low - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    average_true_range = true_range.rolling(window=14, min_periods=14).mean()
    frame["atr_bps"] = average_true_range / close * 10_000.0
    frame["volume_ratio"] = volume / volume.rolling(window=20, min_periods=20).mean()

    typical_price = (high + low + close) / 3.0
    cumulative_volume = volume.cumsum()
    vwap = (typical_price * volume).cumsum() / cumulative_volume
    frame["vwap_distance_bps"] = (close / vwap - 1.0) * 10_000.0

    bar_range = high - low
    frame["range_position"] = (close - low) / bar_range.replace(0.0, np.nan)
    session_open = expected_minute_index(session_date)[0]
    frame["minutes_from_open"] = (
        (frame["available_at"] - session_open).dt.total_seconds() / 60.0
    ).astype("int64")
    return frame.loc[:, FEATURE_COLUMNS]


def compute_feature_frame(bars: pd.DataFrame) -> pd.DataFrame:
    """Compute deterministic features from complete 15-minute bars.

    All rolling state is isolated by symbol and XNYS session.  Calculations
    are backward-looking only, and ``min_periods`` preserves warm-up nulls.
    """
    missing = sorted(_REQUIRED_BAR_COLUMNS.difference(bars.columns))
    if missing:
        raise ValueError("derived bars lack required columns: " + ",".join(missing))
    if bars.empty:
        return pd.DataFrame(columns=FEATURE_COLUMNS)

    require_finite_canonical_numeric_columns(bars)
    frame = bars.loc[:, sorted(_REQUIRED_BAR_COLUMNS)].copy()
    frame["symbol"] = frame["symbol"].astype("string")
    frame["available_at"] = _aware_utc_series(frame["available_at"], field_name="available_at")
    if frame.duplicated(["symbol", "session_date", "available_at"]).any():
        raise ValueError("derived bars must be unique by symbol, session_date, and available_at")

    computed: list[pd.DataFrame] = []
    for (_symbol, raw_session_date), group in frame.groupby(
        ["symbol", "session_date"], sort=True, observed=True
    ):
        session_date = _session_date(raw_session_date)
        local_dates = group["available_at"].dt.tz_convert("America/New_York").dt.date
        if not local_dates.eq(session_date).all():
            raise ValueError("available_at does not match session_date")
        computed.append(_compute_group(group, session_date=session_date))

    return pd.concat(computed, ignore_index=True).sort_values(
        ["symbol", "session_date", "available_at"],
        kind="stable",
        ignore_index=True,
    )


def visible_feature_frame(
    features: pd.DataFrame,
    *,
    clock_time: object,
) -> pd.DataFrame:
    """Return only feature rows available at the supplied aware clock time."""
    missing = sorted(set(FEATURE_COLUMNS).difference(features.columns))
    if missing:
        raise ValueError("feature frame lacks required columns: " + ",".join(missing))
    timestamp = pd.Timestamp(cast(str | int | float | date | datetime, clock_time))
    if timestamp.tzinfo is None:
        raise ValueError("clock_time must be timezone-aware")
    clock_utc = timestamp.tz_convert("UTC")
    available_at = _aware_utc_series(features["available_at"], field_name="available_at")
    visible = features.loc[available_at <= clock_utc, FEATURE_COLUMNS]
    return visible.sort_values(
        ["symbol", "session_date", "available_at"],
        kind="stable",
        ignore_index=True,
    ).copy()
