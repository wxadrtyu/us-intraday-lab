from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class FiveMinuteSourceDeclaration(BaseModel):
    """Closed identity and scope for the approved legacy five-minute member."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Literal["tiingo"]
    feed: Literal["iex"]
    bar_size: Literal["5min"]
    member_name: Literal["price_intraday_vol_5min.csv"]
    member_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    symbols: tuple[Literal["AAPL"], Literal["QQQ"]]
    source_timezone: Literal["America/New_York"]
    expected_start_date: date
    expected_end_date: date
    ingested_at: datetime

    @field_validator("ingested_at")
    @classmethod
    def validate_ingested_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("ingested_at must be aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if self.symbols != ("AAPL", "QQQ"):
            raise ValueError("symbols must be ordered AAPL, QQQ")
        if self.expected_start_date > self.expected_end_date:
            raise ValueError("expected date range must be chronological")
        return self
