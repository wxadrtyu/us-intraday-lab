"""Causal exchange-session resampling for accepted canonical minute bars."""

from __future__ import annotations

from datetime import date
from typing import cast

import pandas as pd

from us_intraday_lab.data.calendar import expected_minute_index
from us_intraday_lab.data.snapshot import DerivedBarSize, DerivedSnapshotLineage

_REQUIRED_COLUMNS = frozenset(
    {"symbol", "timestamp", "open", "high", "low", "close", "volume", "session_date"}
)
_INTERVAL_MINUTES: dict[DerivedBarSize, int] = {"5min": 5, "15min": 15}


def _require_canonical_minute_columns(bars: pd.DataFrame) -> None:
    missing = sorted(_REQUIRED_COLUMNS.difference(bars.columns))
    if missing:
        raise ValueError("minute bars lack required columns: " + ",".join(missing))


def _session_date(value: object) -> date:
    if isinstance(value, date):
        return value
    raise ValueError("session_date must contain date values")


def _complete_interval(
    interval: pd.DataFrame,
    expected_minutes: pd.DatetimeIndex,
    *,
    start: int,
    interval_minutes: int,
) -> bool:
    if len(interval) != interval_minutes:
        return False
    expected = expected_minutes[start : start + interval_minutes]
    actual = pd.DatetimeIndex(interval["timestamp"])
    return actual.equals(expected)


def resample_minute_bars(
    bars: pd.DataFrame,
    *,
    bar_size: DerivedBarSize,
    parent_snapshot_id: str,
) -> pd.DataFrame:
    """Aggregate complete minute intervals anchored at each official XNYS open.

    The ``available_at`` timestamp is the first instant at which every source
    minute in the interval has closed.  Incomplete or non-contiguous intervals
    are deliberately absent rather than filled.
    """
    _require_canonical_minute_columns(bars)
    if bar_size not in _INTERVAL_MINUTES:
        raise ValueError(f"unsupported derived bar size: {bar_size!r}")
    lineage = DerivedSnapshotLineage(
        parent_snapshot_id=parent_snapshot_id,
        bar_size=bar_size,
    )
    if bars.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "available_at",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "session_date",
                "source_bar_size",
                "parent_snapshot_id",
                "bar_size",
            ]
        )

    frame = bars.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    if frame["timestamp"].isna().any():
        raise ValueError("timestamp must not contain missing values")
    interval_minutes = _INTERVAL_MINUTES[bar_size]
    output: list[dict[str, object]] = []

    for (symbol, raw_session_date), group in frame.groupby(
        ["symbol", "session_date"], sort=True, observed=True
    ):
        session_date = _session_date(raw_session_date)
        expected_minutes = expected_minute_index(session_date)
        group = group.sort_values("timestamp", kind="stable").reset_index(drop=True)
        positions = pd.Series(range(len(expected_minutes)), index=expected_minutes)
        minute_positions = group["timestamp"].map(positions)
        valid_minutes = minute_positions.notna()
        if not valid_minutes.all():
            raise ValueError("minute bars must fall within the official XNYS session")
        if any(
            timestamp.tz_convert("America/New_York").date() != session_date
            for timestamp in group["timestamp"]
        ):
            raise ValueError("timestamp does not match session_date")
        group = group.assign(_minute_position=minute_positions.astype("int64"))
        group = group.assign(_interval=group["_minute_position"] // interval_minutes)

        for interval_number, interval in group.groupby("_interval", sort=True, observed=True):
            start = cast(int, interval_number) * interval_minutes
            if not _complete_interval(
                interval,
                expected_minutes,
                start=start,
                interval_minutes=interval_minutes,
            ):
                continue
            output.append(
                {
                    "symbol": str(symbol),
                    "available_at": expected_minutes[start + interval_minutes - 1]
                    + pd.Timedelta(minutes=1),
                    "open": interval["open"].iloc[0],
                    "high": interval["high"].max(),
                    "low": interval["low"].min(),
                    "close": interval["close"].iloc[-1],
                    "volume": interval["volume"].sum(),
                    "session_date": session_date,
                    **lineage.metadata(),
                }
            )

    result = pd.DataFrame(output)
    if result.empty:
        return resample_minute_bars(
            bars.iloc[0:0],
            bar_size=bar_size,
            parent_snapshot_id=parent_snapshot_id,
        )
    return result.sort_values(
        ["symbol", "session_date", "available_at"], kind="stable", ignore_index=True
    )
