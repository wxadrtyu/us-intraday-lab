from datetime import UTC, date, datetime, timedelta
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from us_intraday_lab.contracts.strategies import OrderType

OrderSide = Literal["buy", "sell"]
OrderReasonCode = Literal[
    "entry_signal",
    "exit_signal",
    "stop_loss",
    "take_profit",
    "max_holding",
    "session_close",
]
OrderStatus = Literal[
    "submitted",
    "accepted",
    "partially_filled",
    "filled",
    "cancelled",
    "expired",
    "rejected",
]


class OrderIntent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    schema_version: Literal["1.0.0"]
    run_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    session: date
    side: OrderSide
    order_type: OrderType
    quantity: int = Field(gt=0)
    limit_price: float | None = Field(default=None, gt=0)
    signal_time: datetime
    eligible_time: datetime
    reason_code: OrderReasonCode
    idempotency_key: str = Field(min_length=1)

    @field_validator("signal_time", "eligible_time")
    @classmethod
    def validate_utc_timestamp(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_limit_price(self) -> Self:
        if self.order_type == "limit" and self.limit_price is None:
            raise ValueError("limit_price is required for a limit order")
        if self.order_type == "market" and self.limit_price is not None:
            raise ValueError("limit_price must be absent for a market order")
        return self


class OrderEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    schema_version: Literal["1.0.0"]
    order_id: str = Field(min_length=1)
    previous_status: OrderStatus | None
    status: OrderStatus
    event_time: datetime
    requested_quantity: int = Field(gt=0)
    filled_quantity: int = Field(ge=0)
    requested_price: float | None = Field(default=None, gt=0)
    filled_price: float | None = Field(default=None, gt=0)
    fees: float = Field(ge=0)
    rejection_reason: str | None

    @field_validator("event_time")
    @classmethod
    def validate_utc_timestamp(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("timestamp must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_filled_quantity(self) -> Self:
        if self.filled_quantity > self.requested_quantity:
            raise ValueError("filled_quantity must not exceed requested_quantity")
        return self
