from __future__ import annotations

from datetime import date, datetime
from typing import cast

import numpy as np
import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

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
NUMERIC_CANONICAL_COLUMNS = ("open", "high", "low", "close", "volume")


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


def _numeric_source_column(source: pd.DataFrame, column: str) -> pd.Series:
    values = source[column]
    contains_boolean = (
        is_bool_dtype(values.dtype)
        or values.map(lambda value: isinstance(value, (bool, np.bool_))).any()
    )
    if contains_boolean:
        raise ValueError(f"{column} must contain finite numeric values, not booleans")
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.isna().any() or not np.isfinite(numeric.to_numpy(dtype="float64")).all():
        raise ValueError(f"{column} must contain finite numeric values")
    return numeric.astype("float64")


def require_finite_canonical_numeric_columns(
    bars: pd.DataFrame,
    *,
    columns: tuple[str, ...] = NUMERIC_CANONICAL_COLUMNS,
) -> None:
    """Reject values that do not already satisfy the canonical numeric contract."""
    for column in columns:
        values = bars[column]
        if is_bool_dtype(values.dtype) or not is_numeric_dtype(values.dtype):
            raise TypeError(f"{column} must use a numeric dtype in canonical bars")
        if values.isna().any() or not np.isfinite(values.to_numpy(dtype="float64")).all():
            raise ValueError(f"{column} must contain finite values in canonical bars")


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
    numeric = {
        column: _numeric_source_column(source, column) for column in NUMERIC_CANONICAL_COLUMNS
    }

    bars = pd.DataFrame(
        {
            "symbol": source["ticker"].astype("string").str.strip().str.upper().to_numpy(),
            "timestamp": timestamps,
            "open": numeric["open"].to_numpy(copy=True),
            "high": numeric["high"].to_numpy(copy=True),
            "low": numeric["low"].to_numpy(copy=True),
            "close": numeric["close"].to_numpy(copy=True),
            "volume": numeric["volume"].to_numpy(copy=True),
            "provider": "tiingo",
            "feed": "iex",
            "session_date": timestamps.tz_convert(_NEW_YORK).date,
            "ingested_at": ingestion_timestamp,
        },
        columns=CANONICAL_COLUMNS,
    )
    require_finite_canonical_numeric_columns(bars)
    return bars.sort_values(["symbol", "timestamp"], kind="stable").reset_index(drop=True)
