from __future__ import annotations

from datetime import date, datetime
from typing import cast

import pandas as pd

CANONICAL_COLUMNS = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "provider",
    "feed",
    "session_date",
    "ingested_at",
)
_TIINGO_COLUMNS = ("ticker", "date", "open", "high", "low", "close", "volume")
_NEW_YORK = "America/New_York"


def _as_utc_timestamp(value: object, *, field_name: str) -> pd.Timestamp:
    try:
        timestamp = pd.Timestamp(cast(str | int | float | date | datetime, value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field_name} must be a valid timestamp") from error
    if timestamp.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _duplicate_columns(columns: pd.Index[str]) -> list[str]:
    return columns[columns.duplicated()].unique().tolist()


def canonicalize_tiingo_rows(
    source: pd.DataFrame,
    *,
    ingested_at: object,
) -> pd.DataFrame:
    """Map one Tiingo IEX frame to the canonical minute-bar schema."""
    duplicate_columns = _duplicate_columns(source.columns)
    if duplicate_columns:
        raise ValueError(f"duplicate source columns: {duplicate_columns}")

    missing_columns = sorted(set(_TIINGO_COLUMNS).difference(source.columns))
    if missing_columns:
        raise ValueError(f"missing Tiingo source columns: {missing_columns}")

    ingestion_timestamp = _as_utc_timestamp(ingested_at, field_name="ingested_at")
    timestamps = pd.DatetimeIndex(
        [_as_utc_timestamp(value, field_name="source timestamps") for value in source["date"]]
    )

    bars = pd.DataFrame(
        {
            "symbol": source["ticker"].astype("string").str.strip().str.upper().to_numpy(),
            "timestamp": timestamps,
            "open": source["open"].to_numpy(copy=True),
            "high": source["high"].to_numpy(copy=True),
            "low": source["low"].to_numpy(copy=True),
            "close": source["close"].to_numpy(copy=True),
            "volume": source["volume"].to_numpy(copy=True),
            "provider": "tiingo",
            "feed": "iex",
            "session_date": timestamps.tz_convert(_NEW_YORK).date,
            "ingested_at": ingestion_timestamp,
        },
        columns=CANONICAL_COLUMNS,
    )
    return bars.sort_values(["symbol", "timestamp"], kind="stable").reset_index(drop=True)
