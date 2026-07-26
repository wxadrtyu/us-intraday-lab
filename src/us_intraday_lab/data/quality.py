from collections.abc import Collection
from datetime import date

import pandas as pd
from exchange_calendars.errors import NotSessionError  # type: ignore[import-untyped]

from us_intraday_lab.contracts.datasets import DatasetQuality
from us_intraday_lab.data.calendar import expected_minute_index

PRODUCTION_SYMBOLS = frozenset({"SPY", "QQQ", "IWM"})
_REQUIRED_COLUMNS = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "session_date",
)
_PRICE_COLUMNS = ("open", "high", "low", "close")
_NEW_YORK = "America/New_York"


def _validate_columns(bars: pd.DataFrame) -> None:
    duplicate_columns = bars.columns[bars.columns.duplicated()].unique().tolist()
    if duplicate_columns:
        raise ValueError(f"duplicate canonical columns: {duplicate_columns}")
    missing_columns = sorted(set(_REQUIRED_COLUMNS).difference(bars.columns))
    if missing_columns:
        raise ValueError(f"missing canonical columns: {missing_columns}")


def _utc_timestamps(bars: pd.DataFrame) -> pd.Series:
    timestamps = bars["timestamp"]
    if not isinstance(timestamps.dtype, pd.DatetimeTZDtype):
        raise TypeError("canonical timestamps must be timezone-aware UTC")
    if str(timestamps.dt.tz) != "UTC":
        raise ValueError("canonical timestamps must be timezone-aware UTC")
    return timestamps


def _expected_or_none(session_date: date) -> pd.DatetimeIndex | None:
    try:
        return expected_minute_index(session_date)
    except NotSessionError:
        return None


def _missing_by_symbol_session(
    symbols: pd.Series,
    timestamps: pd.Series,
    session_dates: pd.Series,
) -> dict[tuple[str, date], int]:
    grouped_bars = pd.DataFrame(
        {
            "symbol": symbols,
            "timestamp": timestamps,
            "session_date": session_dates,
        }
    )
    missing: dict[tuple[str, date], int] = {}
    for (symbol, session_date_value), group in grouped_bars.groupby(
        ["symbol", "session_date"],
        sort=False,
        dropna=False,
    ):
        if type(session_date_value) is not date:
            continue
        session_date = session_date_value
        expected = _expected_or_none(session_date)
        if expected is None:
            continue
        observed = pd.DatetimeIndex(group["timestamp"]).intersection(expected).unique()
        missing[(str(symbol).upper(), session_date)] = len(expected.difference(observed))
    return missing


def assess_minute_bars(
    bars: pd.DataFrame,
    *,
    production_symbols: Collection[str] = PRODUCTION_SYMBOLS,
) -> DatasetQuality:
    """Assess canonical minute bars without mutating or filling them.

    Missing production-symbol bars fail the result. Missing robustness-symbol
    bars remain counted so an importer can quarantine each incomplete
    symbol/session while allowing the rest of the snapshot to proceed.
    """
    _validate_columns(bars)
    frame = bars.reset_index(drop=True)
    timestamps = _utc_timestamps(frame)
    symbols = frame["symbol"].astype("string").str.strip().str.upper()
    session_dates = pd.to_datetime(frame["session_date"], errors="coerce").dt.date

    duplicate_rows = int(
        pd.DataFrame({"symbol": symbols, "timestamp": timestamps})
        .duplicated(["symbol", "timestamp"], keep="first")
        .sum()
    )

    prices = frame.loc[:, list(_PRICE_COLUMNS)].apply(pd.to_numeric, errors="coerce")
    invalid_ohlc = (
        prices.isna().any(axis=1)
        | prices.le(0).any(axis=1)
        | prices["high"].lt(prices[["open", "low", "close"]].max(axis=1))
        | prices["low"].gt(prices[["open", "high", "close"]].min(axis=1))
    )
    invalid_ohlc_rows = int(invalid_ohlc.sum())

    volume = pd.to_numeric(frame["volume"], errors="coerce")
    invalid_volume_rows = int((volume.isna() | volume.lt(0)).sum())

    timestamp_session_dates = pd.Series(
        pd.DatetimeIndex(timestamps).tz_convert(_NEW_YORK).date,
        index=frame.index,
    )
    outside_session = session_dates.isna() | session_dates.ne(timestamp_session_dates)
    for session_date in session_dates.dropna().unique():
        matching_rows = session_dates.eq(session_date)
        expected = _expected_or_none(session_date)
        if expected is None:
            outside_session.loc[matching_rows] = True
            continue
        outside_session.loc[matching_rows] |= ~timestamps.loc[matching_rows].isin(expected)
    outside_session_rows = int(outside_session.sum())

    ordering_frame = pd.DataFrame(
        {
            "symbol": symbols,
            "timestamp": timestamps,
            "session_date": session_dates,
        }
    )
    non_monotonic_groups = sum(
        not group.is_monotonic_increasing
        for _, group in ordering_frame.groupby(
            ["symbol", "session_date"],
            sort=False,
            dropna=False,
        )["timestamp"]
    )

    missing_by_group = _missing_by_symbol_session(symbols, timestamps, session_dates)
    missing_expected_bars = sum(missing_by_group.values())
    normalized_production_symbols = {symbol.strip().upper() for symbol in production_symbols}
    production_missing_bars = sum(
        missing_count
        for (symbol, _), missing_count in missing_by_group.items()
        if symbol in normalized_production_symbols
    )

    passed = (
        duplicate_rows == 0
        and invalid_ohlc_rows == 0
        and invalid_volume_rows == 0
        and outside_session_rows == 0
        and non_monotonic_groups == 0
        and production_missing_bars == 0
    )
    return DatasetQuality(
        passed=passed,
        duplicate_rows=duplicate_rows,
        missing_expected_bars=missing_expected_bars,
        invalid_ohlc_rows=invalid_ohlc_rows,
        invalid_volume_rows=invalid_volume_rows,
        outside_session_rows=outside_session_rows,
        non_monotonic_groups=non_monotonic_groups,
    )
