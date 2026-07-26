from collections.abc import Collection
from dataclasses import dataclass
from datetime import date

import pandas as pd
from exchange_calendars.errors import NotSessionError  # type: ignore[import-untyped]

from us_intraday_lab.contracts.datasets import DatasetQuality
from us_intraday_lab.data.calendar import expected_minute_index
from us_intraday_lab.data.canonicalize import require_finite_canonical_numeric_columns

PRODUCTION_SYMBOLS = frozenset({"SPY", "QQQ", "IWM"})
ExpectedGroup = tuple[str, date]
_REQUIRED_COLUMNS = (
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
_PRICE_COLUMNS = ("open", "high", "low", "close")
_NEW_YORK = "America/New_York"


@dataclass(frozen=True, slots=True, order=True)
class SymbolSessionQuality:
    """Deterministic quality result for one canonical symbol/session group."""

    symbol: str
    session_date: date
    production: bool
    expected_bars: int
    observed_bars: int
    missing_expected_bars: int
    duplicate_rows: int
    invalid_ohlc_rows: int
    invalid_volume_rows: int
    outside_session_rows: int
    non_monotonic: bool

    @property
    def structural_passed(self) -> bool:
        return (
            self.duplicate_rows == 0
            and self.invalid_ohlc_rows == 0
            and self.invalid_volume_rows == 0
            and self.outside_session_rows == 0
            and not self.non_monotonic
        )

    @property
    def passed(self) -> bool:
        return self.structural_passed and (not self.production or self.missing_expected_bars == 0)

    @property
    def requires_quarantine(self) -> bool:
        return not self.production and (
            self.missing_expected_bars > 0 or not self.structural_passed
        )


@dataclass(frozen=True, slots=True)
class MinuteBarsQualityAssessment:
    """Aggregate quality plus sorted symbol/session details."""

    aggregate: DatasetQuality
    groups: tuple[SymbolSessionQuality, ...]

    @property
    def passed(self) -> bool:
        return self.aggregate.passed

    @property
    def duplicate_rows(self) -> int:
        return self.aggregate.duplicate_rows

    @property
    def missing_expected_bars(self) -> int:
        return self.aggregate.missing_expected_bars

    @property
    def invalid_ohlc_rows(self) -> int:
        return self.aggregate.invalid_ohlc_rows

    @property
    def invalid_volume_rows(self) -> int:
        return self.aggregate.invalid_volume_rows

    @property
    def outside_session_rows(self) -> int:
        return self.aggregate.outside_session_rows

    @property
    def non_monotonic_groups(self) -> int:
        return self.aggregate.non_monotonic_groups

    @property
    def incomplete_groups(self) -> tuple[SymbolSessionQuality, ...]:
        return tuple(group for group in self.groups if group.missing_expected_bars > 0)


def _validate_columns(bars: pd.DataFrame) -> None:
    duplicate_columns = bars.columns[bars.columns.duplicated()].unique().tolist()
    if duplicate_columns:
        raise ValueError(f"duplicate canonical columns: {duplicate_columns}")
    missing_columns = sorted(set(_REQUIRED_COLUMNS).difference(bars.columns))
    if missing_columns:
        raise ValueError(f"missing canonical columns: {missing_columns}")


def _utc_series(bars: pd.DataFrame, field_name: str) -> pd.Series:
    timestamps = bars[field_name]
    if not isinstance(timestamps.dtype, pd.DatetimeTZDtype):
        raise TypeError(f"{field_name} must be timezone-aware UTC")
    if str(timestamps.dt.tz) != "UTC":
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return timestamps


def _validate_provenance(bars: pd.DataFrame) -> None:
    if bars.empty:
        return
    provenance = bars.loc[:, ["provider", "feed"]].astype("string")
    if provenance.isna().any(axis=None) or provenance.apply(
        lambda values: values.str.strip().eq("")
    ).any(axis=None):
        raise ValueError("provider and feed must be non-empty")
    if len(provenance.drop_duplicates()) != 1:
        raise ValueError("canonical dataset must contain exactly one provider/feed pair")
    _utc_series(bars, "ingested_at")


def _expected_or_none(session_date: date) -> pd.DatetimeIndex | None:
    try:
        return expected_minute_index(session_date)
    except NotSessionError:
        return None


def _normalized_expected_groups(
    expected_groups: Collection[ExpectedGroup] | None,
) -> set[ExpectedGroup]:
    normalized: set[ExpectedGroup] = set()
    if expected_groups is None:
        return normalized
    for symbol, session_date in expected_groups:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("expected group symbol must be non-empty")
        if type(session_date) is not date:
            raise TypeError("expected group session_date must be a date")
        if _expected_or_none(session_date) is None:
            raise ValueError(f"expected group is not an XNYS session: {session_date}")
        normalized.add((normalized_symbol, session_date))
    return normalized


def _observed_groups(symbols: pd.Series, session_dates: pd.Series) -> set[ExpectedGroup]:
    groups: set[ExpectedGroup] = set()
    for symbol, session_date in zip(symbols.tolist(), session_dates.tolist(), strict=True):
        if type(session_date) is not date:
            raise ValueError("session_date must contain valid dates")
        groups.add((str(symbol), session_date))
    return groups


def _group_results(
    *,
    symbols: pd.Series,
    timestamps: pd.Series,
    session_dates: pd.Series,
    duplicate_mask: pd.Series,
    invalid_ohlc_mask: pd.Series,
    invalid_volume_mask: pd.Series,
    all_groups: Collection[ExpectedGroup],
    production_symbols: Collection[str],
    source_non_monotonic_groups: Collection[ExpectedGroup],
) -> tuple[SymbolSessionQuality, ...]:
    normalized_production = {symbol.strip().upper() for symbol in production_symbols}
    source_non_monotonic = set(source_non_monotonic_groups)
    results: list[SymbolSessionQuality] = []
    for symbol, session_date in sorted(all_groups):
        group_rows = symbols.eq(symbol) & session_dates.eq(session_date)
        group_timestamps = timestamps.loc[group_rows]
        expected = _expected_or_none(session_date)
        expected_bars = 0 if expected is None else len(expected)
        if expected is None:
            observed_bars = 0
            missing_expected_bars = 0
            outside_session_rows = int(group_rows.sum())
        else:
            observed = pd.DatetimeIndex(group_timestamps).intersection(expected).unique()
            observed_bars = len(observed)
            missing_expected_bars = len(expected.difference(observed))
            timestamp_session_dates = pd.Series(
                pd.DatetimeIndex(group_timestamps).tz_convert(_NEW_YORK).date,
                index=group_timestamps.index,
            )
            outside_session_rows = int(
                (timestamp_session_dates.ne(session_date) | ~group_timestamps.isin(expected)).sum()
            )
        results.append(
            SymbolSessionQuality(
                symbol=symbol,
                session_date=session_date,
                production=symbol in normalized_production,
                expected_bars=expected_bars,
                observed_bars=observed_bars,
                missing_expected_bars=missing_expected_bars,
                duplicate_rows=int(duplicate_mask.loc[group_rows].sum()),
                invalid_ohlc_rows=int(invalid_ohlc_mask.loc[group_rows].sum()),
                invalid_volume_rows=int(invalid_volume_mask.loc[group_rows].sum()),
                outside_session_rows=outside_session_rows,
                non_monotonic=(
                    (symbol, session_date) in source_non_monotonic
                    or not group_timestamps.is_monotonic_increasing
                ),
            )
        )
    return tuple(results)


def _aggregate_quality(
    groups: Collection[SymbolSessionQuality],
) -> DatasetQuality:
    duplicate_rows = sum(group.duplicate_rows for group in groups)
    missing_expected_bars = sum(group.missing_expected_bars for group in groups)
    invalid_ohlc_rows = sum(group.invalid_ohlc_rows for group in groups)
    invalid_volume_rows = sum(group.invalid_volume_rows for group in groups)
    outside_session_rows = sum(group.outside_session_rows for group in groups)
    non_monotonic_groups = sum(group.non_monotonic for group in groups)
    production_missing_bars = sum(
        group.missing_expected_bars for group in groups if group.production
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


def assess_minute_bars(
    bars: pd.DataFrame,
    *,
    expected_groups: Collection[ExpectedGroup] | None = None,
    production_symbols: Collection[str] = PRODUCTION_SYMBOLS,
    source_non_monotonic_groups: Collection[ExpectedGroup] = (),
) -> MinuteBarsQualityAssessment:
    """Assess canonical minute bars without mutating or filling them.

    Declared expected groups make wholly absent symbol/sessions measurable.
    Missing production groups fail the aggregate. Missing robustness groups
    expose ``requires_quarantine`` without altering the input bars.
    """
    _validate_columns(bars)
    frame = bars.reset_index(drop=True)
    _validate_provenance(frame)
    require_finite_canonical_numeric_columns(frame)
    timestamps = _utc_series(frame, "timestamp")
    symbols = frame["symbol"].astype("string").str.strip().str.upper()
    if symbols.isna().any() or symbols.eq("").any():
        raise ValueError("symbol must be non-empty")
    session_dates = pd.to_datetime(frame["session_date"], errors="coerce").dt.date

    duplicate_mask = pd.DataFrame({"symbol": symbols, "timestamp": timestamps}).duplicated(
        ["symbol", "timestamp"],
        keep="first",
    )
    prices = frame.loc[:, list(_PRICE_COLUMNS)]
    invalid_ohlc_mask = (
        prices.isna().any(axis=1)
        | prices.le(0).any(axis=1)
        | prices["high"].lt(prices[["open", "low", "close"]].max(axis=1))
        | prices["low"].gt(prices[["open", "high", "close"]].min(axis=1))
    )
    volume = frame["volume"]
    invalid_volume_mask = volume.isna() | volume.lt(0)

    all_groups = _observed_groups(symbols, session_dates)
    all_groups.update(_normalized_expected_groups(expected_groups))
    groups = _group_results(
        symbols=symbols,
        timestamps=timestamps,
        session_dates=session_dates,
        duplicate_mask=duplicate_mask,
        invalid_ohlc_mask=invalid_ohlc_mask,
        invalid_volume_mask=invalid_volume_mask,
        all_groups=all_groups,
        production_symbols=production_symbols,
        source_non_monotonic_groups=source_non_monotonic_groups,
    )
    return MinuteBarsQualityAssessment(
        aggregate=_aggregate_quality(groups),
        groups=groups,
    )
