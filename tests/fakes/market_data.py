"""Deterministic Alpaca IEX minute-bar fixtures."""

from __future__ import annotations

from datetime import datetime, timedelta

from us_intraday_lab.contracts.market import MarketBarClosed


def iex_minute_bar(
    *,
    symbol: str,
    bar_start: datetime,
    price: float = 100.0,
    volume: int = 1_000,
    event_suffix: str = "",
) -> MarketBarClosed:
    return MarketBarClosed(
        provider_event_id=(
            f"iex:{symbol}:{bar_start.isoformat()}" + (f":{event_suffix}" if event_suffix else "")
        ),
        symbol=symbol,
        timeframe="1min",
        bar_start=bar_start,
        bar_end=bar_start + timedelta(minutes=1),
        available_at=bar_start + timedelta(minutes=1),
        open=price,
        high=price + 0.25,
        low=price - 0.25,
        close=price + 0.10,
        volume=volume,
    )


class FakeIexMarketData:
    def __init__(self, bars: tuple[MarketBarClosed, ...]) -> None:
        self._bars = bars
        self.subscriptions: list[tuple[str, ...]] = []

    def subscribe(self, symbols: tuple[str, ...]) -> None:
        self.subscriptions.append(symbols)

    def stream(self) -> tuple[MarketBarClosed, ...]:
        return self._bars
