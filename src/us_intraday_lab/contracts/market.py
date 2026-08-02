"""Versioned paper-market events with explicit provider and feed lineage."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MarketBarClosed(BaseModel):
    """One completed Alpaca IEX bar that is safe for strategy evaluation."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    schema_version: Literal["1.0.0"] = "1.0.0"
    provider_event_id: str = Field(min_length=1)
    provider: Literal["alpaca"] = "alpaca"
    feed: Literal["iex"] = "iex"
    symbol: Literal["SPY", "QQQ", "IWM"]
    timeframe: Literal["1min", "15min"]
    bar_start: datetime
    bar_end: datetime
    available_at: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: int = Field(ge=0)

    @field_validator("bar_start", "bar_end", "available_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_bar(self) -> Self:
        duration = timedelta(minutes=1 if self.timeframe == "1min" else 15)
        if self.bar_end - self.bar_start != duration:
            raise ValueError("bar interval must match timeframe")
        if self.available_at < self.bar_end:
            raise ValueError("available_at must not precede bar_end")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be the greatest OHLC value")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be the least OHLC value")
        return self
