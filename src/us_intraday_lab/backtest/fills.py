"""Deterministic next-minute market and conservative limit fills."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import isfinite
from typing import Literal

from us_intraday_lab.backtest.costs import CostModel
from us_intraday_lab.contracts.orders import OrderIntent


@dataclass(frozen=True)
class MinuteBar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must be non-empty")
        if self.timestamp.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be timezone-aware UTC")
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(UTC))
        prices = (self.open, self.high, self.low, self.close)
        if not all(isfinite(price) and price > 0 for price in prices):
            raise ValueError("bar prices must be finite and positive")
        if self.low > min(self.open, self.close) or self.high < max(self.open, self.close):
            raise ValueError("bar OHLC values are inconsistent")
        if self.low > self.high:
            raise ValueError("bar low must not exceed high")


@dataclass(frozen=True)
class Fill:
    order_key: str
    symbol: str
    side: Literal["buy", "sell"]
    quantity: int
    price: float
    fees: float
    fill_time: datetime


class FillSimulator:
    """Apply one cost scenario to an eligible order and minute bar."""

    def __init__(self, cost_model: CostModel) -> None:
        self.cost_model = cost_model

    def try_fill(self, order: OrderIntent, bar: MinuteBar) -> Fill | None:
        if order.eligible_time < order.signal_time + timedelta(minutes=1):
            raise ValueError("eligible_time must be at least one minute after signal_time")
        if bar.symbol != order.symbol:
            raise ValueError("bar symbol must match order symbol")
        if bar.timestamp < order.eligible_time:
            return None

        price: float
        if order.order_type == "market":
            direction = 1.0 if order.side == "buy" else -1.0
            price = bar.open * (1.0 + direction * self.cost_model.price_impact_bps / 10_000)
        else:
            if order.limit_price is None:
                raise ValueError("limit order requires limit_price")
            crossed = (
                bar.low <= order.limit_price
                if order.side == "buy"
                else bar.high >= order.limit_price
            )
            if not crossed:
                return None
            # OHLC does not reveal the intrabar path. Filling at the submitted
            # limit deliberately declines any possible price improvement.
            price = order.limit_price

        return Fill(
            order_key=order.idempotency_key,
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=price,
            fees=order.quantity * self.cost_model.commission_per_share_usd,
            fill_time=bar.timestamp,
        )
