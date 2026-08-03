"""Alpaca IEX minute-bar validation, bounded reordering, and closed aggregation."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from itertools import pairwise
from typing import Any, Literal, Protocol, cast

from us_intraday_lab.contracts.market import MarketBarClosed
from us_intraday_lab.data.calendar import expected_minute_index
from us_intraday_lab.paper.store import PaperStore
from us_intraday_lab.strategy.features import FEATURE_SET_VERSION

MARKET_SCHEMA_VERSION = "1.0.0"
PRODUCTION_SYMBOLS = frozenset({"SPY", "QQQ", "IWM"})
PAPER_KEY_VARIABLE = "ALPACA_PAPER_API_KEY"
PAPER_SECRET_VARIABLE = "ALPACA_PAPER_SECRET_KEY"


class _StockStream(Protocol):
    def subscribe_bars(self, handler: object, *symbols: str) -> None: ...

    def run(self) -> None: ...


StockStreamFactory = Callable[[str, str], _StockStream]


def _stock_stream_factory(api_key: str, secret_key: str) -> _StockStream:
    from alpaca.data.enums import DataFeed
    from alpaca.data.live import StockDataStream

    return cast(
        _StockStream,
        StockDataStream(api_key, secret_key, feed=DataFeed.IEX),
    )


@dataclass(frozen=True, slots=True)
class IexSubscription:
    symbols: tuple[Literal["SPY", "QQQ", "IWM"], ...]
    provider: Literal["alpaca"] = "alpaca"
    feed: Literal["iex"] = "iex"

    def __post_init__(self) -> None:
        if not self.symbols or any(symbol not in PRODUCTION_SYMBOLS for symbol in self.symbols):
            raise ValueError("PRODUCTION_SYMBOL_SUBSCRIPTION_REQUIRED")
        if len(self.symbols) != len(set(self.symbols)):
            raise ValueError("PRODUCTION_SYMBOL_SUBSCRIPTION_MUST_BE_UNIQUE")


@dataclass(frozen=True, slots=True)
class ProviderTransitionDiagnostic:
    symbol: str
    compared_provider: str
    compared_feed: str
    observed_at: datetime
    difference_bps: float

    def __post_init__(self) -> None:
        if self.symbol not in PRODUCTION_SYMBOLS:
            raise ValueError("PRODUCTION_SYMBOL_REQUIRED")
        if self.observed_at.utcoffset() != timedelta(0):
            raise ValueError("observed_at must be timezone-aware UTC")


@dataclass(frozen=True, slots=True)
class MarketDataHealth:
    entries_enabled: bool
    reason_codes: tuple[str, ...]
    observed_at: datetime


class MarketDataPipeline:
    """Persist valid IEX minutes and emit complete session-anchored 15m bars."""

    def __init__(
        self,
        *,
        store: PaperStore,
        paper_session_id: str,
        session_date: date,
        reorder_window: timedelta,
        stale_after: timedelta,
        expected_market_schema_version: str,
        expected_feature_set_version: str,
        required_symbols: tuple[Literal["SPY", "QQQ", "IWM"], ...] = (
            "SPY",
            "QQQ",
            "IWM",
        ),
    ) -> None:
        if expected_market_schema_version != MARKET_SCHEMA_VERSION:
            raise RuntimeError("MARKET_SCHEMA_VERSION_MISMATCH")
        if expected_feature_set_version != FEATURE_SET_VERSION:
            raise RuntimeError("FEATURE_SET_VERSION_MISMATCH")
        if reorder_window <= timedelta(0) or stale_after <= timedelta(0):
            raise ValueError("market-data windows must be positive")
        IexSubscription(symbols=required_symbols)
        session = store.get_session(paper_session_id)
        if session is None or session.session_date != session_date:
            raise ValueError("PAPER_SESSION_DATE_MISMATCH")
        official = tuple(
            timestamp.to_pydatetime().astimezone(UTC)
            for timestamp in expected_minute_index(session_date)
        )
        if not official:
            raise ValueError("session_date must be an official XNYS session")
        self.store = store
        self.paper_session_id = paper_session_id
        self.session_date = session_date
        self.reorder_window = reorder_window
        self.stale_after = stale_after
        self.required_symbols = required_symbols
        self._official_minutes = frozenset(official)
        self._session_open = official[0]
        self._bars: dict[tuple[str, datetime], MarketBarClosed] = {}
        self._latest_by_symbol: dict[str, datetime] = {}
        self._emitted_buckets: set[tuple[str, datetime]] = set()
        self._diagnostics: list[ProviderTransitionDiagnostic] = []
        self._circuit_reasons: set[str] = set()
        for event in store.list_market_events(paper_session_id):
            if event.timeframe == "1min":
                self._bars[(event.symbol, event.bar_start)] = event
                latest = self._latest_by_symbol.get(event.symbol)
                if latest is None or event.bar_start > latest:
                    self._latest_by_symbol[event.symbol] = event.bar_start
            else:
                self._emitted_buckets.add((event.symbol, event.bar_start))

    @property
    def provider_transition_diagnostics(self) -> tuple[ProviderTransitionDiagnostic, ...]:
        return tuple(self._diagnostics)

    def record_provider_transition_diagnostic(
        self, diagnostic: ProviderTransitionDiagnostic
    ) -> None:
        self._diagnostics.append(diagnostic)

    def ingest(self, bar: MarketBarClosed) -> tuple[MarketBarClosed, ...]:
        if type(bar) is not MarketBarClosed or bar.timeframe != "1min":
            raise TypeError("IEX_ONE_MINUTE_BAR_REQUIRED")
        if bar.symbol not in PRODUCTION_SYMBOLS:
            raise ValueError("PRODUCTION_SYMBOL_REQUIRED")
        if bar.bar_start not in self._official_minutes:
            self._circuit_reasons.add("OUTSIDE_OFFICIAL_SESSION")
            raise ValueError("OUTSIDE_OFFICIAL_SESSION")

        key = (bar.symbol, bar.bar_start)
        existing = self._bars.get(key)
        if existing is not None:
            if existing != bar:
                self._circuit_reasons.add("DUPLICATE_BAR_CONTENT_MISMATCH")
                raise ValueError("DUPLICATE_BAR_CONTENT_MISMATCH")
            return ()
        latest = self._latest_by_symbol.get(bar.symbol)
        if latest is not None and bar.bar_start < latest - self.reorder_window:
            self._circuit_reasons.add("BAR_OUTSIDE_REORDER_WINDOW")
            raise ValueError("BAR_OUTSIDE_REORDER_WINDOW")

        self._bars[key] = bar
        if latest is None or bar.bar_start > latest:
            self._latest_by_symbol[bar.symbol] = bar.bar_start
        self.store.append_market_event(self.paper_session_id, bar)
        aggregate = self._aggregate_if_complete(symbol=bar.symbol, timestamp=bar.bar_start)
        if aggregate is None:
            return ()
        self.store.append_market_event(self.paper_session_id, aggregate)
        return (aggregate,)

    def _aggregate_if_complete(self, *, symbol: str, timestamp: datetime) -> MarketBarClosed | None:
        offset = int((timestamp - self._session_open).total_seconds() // 60)
        bucket_start = self._session_open + timedelta(minutes=(offset // 15) * 15)
        bucket_key = (symbol, bucket_start)
        if bucket_key in self._emitted_buckets:
            return None
        starts = tuple(bucket_start + timedelta(minutes=index) for index in range(15))
        components = tuple(self._bars.get((symbol, start)) for start in starts)
        if any(item is None for item in components):
            return None
        bars = tuple(item for item in components if item is not None)
        identity = "|".join(item.provider_event_id for item in bars)
        aggregate = MarketBarClosed(
            provider_event_id="iex15:" + hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            symbol=cast(Literal["SPY", "QQQ", "IWM"], symbol),
            timeframe="15min",
            bar_start=bucket_start,
            bar_end=bucket_start + timedelta(minutes=15),
            available_at=max(item.available_at for item in bars),
            open=bars[0].open,
            high=max(item.high for item in bars),
            low=min(item.low for item in bars),
            close=bars[-1].close,
            volume=sum(item.volume for item in bars),
        )
        self._emitted_buckets.add(bucket_key)
        return aggregate

    def health(self, *, observed_at: datetime) -> MarketDataHealth:
        if observed_at.utcoffset() != timedelta(0):
            raise ValueError("observed_at must be timezone-aware UTC")
        reasons = set(self._circuit_reasons)
        if any(symbol not in self._latest_by_symbol for symbol in self.required_symbols):
            reasons.add("REQUIRED_SYMBOL_STREAM_MISSING")
        for symbol, latest_start in self._latest_by_symbol.items():
            starts = sorted(
                timestamp
                for candidate_symbol, timestamp in self._bars
                if candidate_symbol == symbol
            )
            if any(later - earlier > timedelta(minutes=1) for earlier, later in pairwise(starts)):
                reasons.add("MARKET_DATA_GAP")
            latest = self._bars[(symbol, latest_start)]
            if observed_at - latest.available_at > self.stale_after:
                reasons.add("MARKET_DATA_STALE")
        if not self._latest_by_symbol:
            reasons.add("MARKET_DATA_STALE")
        return MarketDataHealth(
            entries_enabled=not reasons,
            reason_codes=tuple(sorted(reasons)),
            observed_at=observed_at,
        )


class AlpacaIexMinuteStream:
    """The only production paper-market stream: Alpaca StockDataStream on IEX."""

    def __init__(self, *, stream: _StockStream, subscription: IexSubscription) -> None:
        self._stream = stream
        self.subscription = subscription

    @classmethod
    def from_environment(
        cls,
        *,
        symbols: tuple[Literal["SPY", "QQQ", "IWM"], ...] = ("SPY", "QQQ", "IWM"),
        environ: Mapping[str, str] | None = None,
        stream_factory: StockStreamFactory = _stock_stream_factory,
    ) -> AlpacaIexMinuteStream:
        values = os.environ if environ is None else environ
        api_key = values.get(PAPER_KEY_VARIABLE, "")
        secret_key = values.get(PAPER_SECRET_VARIABLE, "")
        if not api_key or not secret_key:
            raise RuntimeError("PAPER_MARKET_DATA_CREDENTIAL_MISSING")
        return cls(
            stream=stream_factory(api_key, secret_key),
            subscription=IexSubscription(symbols=symbols),
        )

    @staticmethod
    def _map_bar(raw: Any) -> MarketBarClosed:
        timestamp = getattr(raw, "timestamp", None)
        if not isinstance(timestamp, datetime) or timestamp.utcoffset() is None:
            raise ValueError("ALPACA_IEX_BAR_TIMESTAMP_INVALID")
        start = timestamp.astimezone(UTC)
        end = start + timedelta(minutes=1)
        symbol = str(getattr(raw, "symbol", ""))
        identity = f"{symbol}|{start.isoformat()}"
        return MarketBarClosed(
            provider_event_id="alpaca-iex-" + hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            symbol=cast(Literal["SPY", "QQQ", "IWM"], symbol),
            timeframe="1min",
            bar_start=start,
            bar_end=end,
            available_at=max(end, datetime.now(UTC)),
            open=float(raw.open),
            high=float(raw.high),
            low=float(raw.low),
            close=float(raw.close),
            volume=int(raw.volume),
        )

    def run(self, handler: Callable[[MarketBarClosed], None]) -> None:
        async def on_bar(raw: Any) -> None:
            handler(self._map_bar(raw))

        self._stream.subscribe_bars(on_bar, *self.subscription.symbols)
        self._stream.run()
