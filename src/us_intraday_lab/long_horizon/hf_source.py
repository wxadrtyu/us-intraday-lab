from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import pandas as pd

_SOURCE_COLUMNS = ("ticker", "timestamp", "open", "high", "low", "close", "volume")
_OUTPUT_COLUMNS = (
    "symbol",
    "timestamp",
    "available_at",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "session_date",
)


@dataclass(frozen=True, slots=True)
class HfAggregationResult:
    bars: pd.DataFrame
    accepted_sessions: tuple[date, ...]
    rejected_sessions: tuple[date, ...]


def _empty_bars() -> pd.DataFrame:
    return pd.DataFrame(columns=list(_OUTPUT_COLUMNS))


def aggregate_hf_regular_minutes(
    frame: pd.DataFrame,
    *,
    symbols: tuple[str, str],
    expected_minutes_per_session: int = 390,
) -> HfAggregationResult:
    """Filter UTC source rows to XNYS regular hours and form completed 5m bars."""

    if type(frame) is not pd.DataFrame:
        raise TypeError("frame must be an exact pandas DataFrame")
    if type(symbols) is not tuple or len(symbols) != 2 or len(set(symbols)) != 2:
        raise ValueError("symbols must be an exact pair of distinct tickers")
    if any(type(symbol) is not str or not symbol for symbol in symbols):
        raise ValueError("symbols must contain non-empty exact strings")
    if (
        type(expected_minutes_per_session) is not int
        or expected_minutes_per_session <= 0
        or expected_minutes_per_session % 5
    ):
        raise ValueError("expected_minutes_per_session must be a positive multiple of five")
    missing = sorted(set(_SOURCE_COLUMNS).difference(str(column) for column in frame.columns))
    if missing:
        raise ValueError("HF source lacks required columns: " + ",".join(missing))
    retained = frame.loc[frame["ticker"].isin(symbols), list(_SOURCE_COLUMNS)].copy()
    if retained.empty or set(retained["ticker"].astype(str)) != set(symbols):
        raise ValueError("HF source must contain both requested symbols")
    retained["timestamp"] = pd.to_datetime(retained["timestamp"], utc=True, errors="raise")
    for column in ("open", "high", "low", "close", "volume"):
        retained[column] = pd.to_numeric(retained[column], errors="raise").astype("float64")
        if any(not math.isfinite(float(value)) for value in retained[column]):
            raise ValueError(f"{column} must contain finite values")
    invalid = (
        (retained[["open", "high", "low", "close"]] <= 0.0).any(axis=1)
        | (retained["high"] < retained[["open", "close", "low"]].max(axis=1))
        | (retained["low"] > retained[["open", "close", "high"]].min(axis=1))
        | (retained["volume"] < 0.0)
    )
    if invalid.any():
        raise ValueError("HF source contains invalid OHLCV rows")
    eastern = retained["timestamp"].dt.tz_convert("America/New_York")
    minute_of_day = eastern.dt.hour * 60 + eastern.dt.minute
    retained = retained.loc[(minute_of_day >= 570) & (minute_of_day < 960)].copy()
    eastern = retained["timestamp"].dt.tz_convert("America/New_York")
    retained["session_date"] = eastern.dt.date
    retained["minute_offset"] = eastern.dt.hour * 60 + eastern.dt.minute - 570

    observed_sessions = tuple(sorted(retained["session_date"].unique()))
    accepted: list[date] = []
    rejected: list[date] = []
    expected_offsets = tuple(range(expected_minutes_per_session))
    for session in observed_sessions:
        complete = True
        for symbol in symbols:
            offsets = tuple(
                sorted(
                    int(value)
                    for value in retained.loc[
                        (retained["session_date"] == session)
                        & (retained["ticker"] == symbol),
                        "minute_offset",
                    ]
                )
            )
            if offsets != expected_offsets:
                complete = False
                break
        (accepted if complete else rejected).append(session)
    if not accepted:
        return HfAggregationResult(_empty_bars(), (), tuple(rejected))

    retained = retained.loc[retained["session_date"].isin(accepted)].copy()
    retained["bucket"] = retained["minute_offset"] // 5
    grouped = retained.sort_values(["ticker", "timestamp"], kind="stable").groupby(
        ["ticker", "session_date", "bucket"], sort=True, observed=True
    )
    bars = grouped.agg(
        timestamp=("timestamp", "first"),
        available_at=("timestamp", lambda values: values.iloc[-1] + pd.Timedelta(minutes=1)),
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    ).reset_index()
    bars = bars.rename(columns={"ticker": "symbol"}).drop(columns=["bucket"])
    bars = bars.loc[:, list(_OUTPUT_COLUMNS)].sort_values(
        ["session_date", "timestamp", "symbol"], kind="stable", ignore_index=True
    )
    expected_bars = len(accepted) * len(symbols) * (expected_minutes_per_session // 5)
    if len(bars) != expected_bars:
        raise RuntimeError("accepted HF sessions did not produce the expected five-minute grid")
    return HfAggregationResult(bars, tuple(accepted), tuple(rejected))
