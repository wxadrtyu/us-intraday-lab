"""Frozen contracts for paper-broker state, risk evidence, and reports."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from types import MappingProxyType
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from us_intraday_lab.contracts.orders import OrderSide, OrderStatus

PaperOrderStatus = OrderStatus
PaperSymbol = Literal["SPY", "QQQ", "IWM"]


class _PaperModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


def _utc(value: datetime, *, field_name: str) -> datetime:
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return value.astimezone(UTC)


class PaperSession(_PaperModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    paper_session_id: str = Field(min_length=1)
    session_date: date
    environment: Literal["paper"] = "paper"
    broker_endpoint: Literal["https://paper-api.alpaca.markets"] = (
        "https://paper-api.alpaca.markets"
    )
    broker_account_id: str = Field(min_length=1)
    broker_sdk_version: str = Field(min_length=1)
    market_provider: Literal["alpaca"] = "alpaca"
    market_feed: Literal["iex"] = "iex"
    production_symbols: tuple[PaperSymbol, PaperSymbol, PaperSymbol] = (
        "SPY",
        "QQQ",
        "IWM",
    )
    status: Literal["initializing", "running", "closeout", "closed", "blocked"] = "initializing"
    created_at: datetime

    @field_validator("production_symbols")
    @classmethod
    def validate_symbols(
        cls, value: tuple[PaperSymbol, PaperSymbol, PaperSymbol]
    ) -> tuple[PaperSymbol, PaperSymbol, PaperSymbol]:
        if value != ("SPY", "QQQ", "IWM"):
            raise ValueError("production_symbols must be exactly SPY, QQQ, IWM")
        return value

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _utc(value, field_name="created_at")


class BrokerAccount(_PaperModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    environment: Literal["paper"] = "paper"
    account_id: str = Field(min_length=1)
    account_number: str = Field(min_length=1)
    broker_sdk_version: str = Field(min_length=1)
    status: Literal["ACTIVE", "PAPER_ONLY"]
    currency: Literal["USD"] = "USD"
    cash: float = Field(ge=0)
    buying_power: float = Field(ge=0)
    equity: float = Field(ge=0)
    trading_blocked: bool
    account_blocked: bool
    trade_suspended_by_user: bool
    multiplier: int = Field(ge=1, le=4)
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return _utc(value, field_name="observed_at")


class BrokerClock(_PaperModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    environment: Literal["paper"] = "paper"
    observed_at: datetime
    is_open: bool
    next_open: datetime
    next_close: datetime

    @field_validator("observed_at", "next_open", "next_close")
    @classmethod
    def validate_timestamps(cls, value: datetime, info: object) -> datetime:
        field_name = getattr(info, "field_name", "timestamp")
        return _utc(value, field_name=field_name)

    @model_validator(mode="after")
    def validate_clock(self) -> Self:
        if self.next_close <= self.observed_at:
            raise ValueError("next_close must be after observed_at")
        return self


class BrokerOrder(_PaperModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    environment: Literal["paper"] = "paper"
    broker_order_id: str = Field(min_length=1)
    client_order_id: str = Field(min_length=1)
    symbol: PaperSymbol
    side: OrderSide
    order_type: Literal["market", "limit"]
    status: PaperOrderStatus
    quantity: int = Field(gt=0)
    filled_quantity: int = Field(ge=0)
    average_fill_price: float | None = Field(default=None, gt=0)
    submitted_at: datetime
    updated_at: datetime
    rejection_reason: str | None

    @field_validator("submitted_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime, info: object) -> datetime:
        field_name = getattr(info, "field_name", "timestamp")
        return _utc(value, field_name=field_name)

    @model_validator(mode="after")
    def validate_fill(self) -> Self:
        if self.filled_quantity > self.quantity:
            raise ValueError("filled_quantity must not exceed quantity")
        if self.updated_at < self.submitted_at:
            raise ValueError("updated_at must not precede submitted_at")
        if self.filled_quantity and self.average_fill_price is None:
            raise ValueError("average_fill_price is required for a fill")
        return self


class BrokerPosition(_PaperModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    environment: Literal["paper"] = "paper"
    asset_id: str = Field(min_length=1)
    symbol: PaperSymbol
    quantity: int = Field(gt=0)
    average_entry_price: float = Field(gt=0)
    market_value: float = Field(ge=0)
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return _utc(value, field_name="observed_at")


class PositionSnapshot(_PaperModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    snapshot_id: str = Field(min_length=1)
    paper_session_id: str = Field(min_length=1)
    source: Literal["broker"] = "broker"
    positions: tuple[BrokerPosition, ...]
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return _utc(value, field_name="observed_at")

    @model_validator(mode="after")
    def validate_unique_symbols(self) -> Self:
        symbols = tuple(item.symbol for item in self.positions)
        if len(symbols) != len(set(symbols)):
            raise ValueError("positions must contain unique symbols")
        return self


class PaperCheckpoint(_PaperModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    checkpoint_id: str = Field(min_length=1)
    paper_session_id: str = Field(min_length=1)
    event_sequence: int = Field(ge=0)
    state_sha256: str
    created_at: datetime

    @field_validator("state_sha256")
    @classmethod
    def validate_hash(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("state_sha256 must be a lowercase SHA-256 digest")
        return value

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _utc(value, field_name="created_at")


class RiskDecision(_PaperModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    decision_id: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    approved: bool
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    observed_values: Mapping[str, float | int | bool | str]
    decided_at: datetime

    @field_validator("observed_values", mode="after")
    @classmethod
    def freeze_observed(
        cls, value: Mapping[str, float | int | bool | str]
    ) -> Mapping[str, float | int | bool | str]:
        if any(not key for key in value):
            raise ValueError("observed_values keys must be non-empty")
        return MappingProxyType(dict(sorted(value.items())))

    @field_serializer("observed_values")
    def serialize_observed(
        self, value: Mapping[str, float | int | bool | str]
    ) -> dict[str, float | int | bool | str]:
        return dict(value)

    @field_validator("decided_at")
    @classmethod
    def validate_decided_at(cls, value: datetime) -> datetime:
        return _utc(value, field_name="decided_at")


class IncidentEvent(_PaperModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    incident_id: str = Field(min_length=1)
    paper_session_id: str = Field(min_length=1)
    severity: Literal["info", "warning", "critical"]
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    observed_values: Mapping[str, float | int | bool | str]
    occurred_at: datetime

    @field_validator("observed_values", mode="after")
    @classmethod
    def freeze_observed(
        cls, value: Mapping[str, float | int | bool | str]
    ) -> Mapping[str, float | int | bool | str]:
        if any(not key for key in value):
            raise ValueError("observed_values keys must be non-empty")
        return MappingProxyType(dict(sorted(value.items())))

    @field_serializer("observed_values")
    def serialize_observed(
        self, value: Mapping[str, float | int | bool | str]
    ) -> dict[str, float | int | bool | str]:
        return dict(value)

    @field_validator("occurred_at")
    @classmethod
    def validate_occurred_at(cls, value: datetime) -> datetime:
        return _utc(value, field_name="occurred_at")


class ReconciliationResult(_PaperModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    reconciliation_id: str = Field(min_length=1)
    paper_session_id: str = Field(min_length=1)
    status: Literal["clean", "recoverable", "blocked"]
    entries_enabled: bool
    exits_enabled: bool
    discrepancy_codes: tuple[str, ...]
    startup_steps: tuple[str, ...]
    broker_account_id: str = Field(min_length=1)
    local_state_sha256: str
    broker_state_sha256: str
    completed_at: datetime

    @field_validator("discrepancy_codes", "startup_steps")
    @classmethod
    def validate_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(re.fullmatch(r"[A-Z][A-Z0-9_]*", item) is None for item in value):
            raise ValueError("codes must contain stable uppercase values")
        return value

    @field_validator("local_state_sha256", "broker_state_sha256")
    @classmethod
    def validate_state_hash(cls, value: str) -> str:
        if re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError("state hash must be a lowercase SHA-256 digest")
        return value

    @field_validator("completed_at")
    @classmethod
    def validate_completed_at(cls, value: datetime) -> datetime:
        return _utc(value, field_name="completed_at")

    @model_validator(mode="after")
    def validate_permissions(self) -> Self:
        if not self.exits_enabled:
            raise ValueError("reconciliation must always leave exits enabled")
        if self.entries_enabled != (self.status == "clean"):
            raise ValueError("entries may be enabled only for clean reconciliation")
        if self.status == "clean" and self.discrepancy_codes:
            raise ValueError("clean reconciliation cannot contain discrepancies")
        if self.status != "clean" and not self.discrepancy_codes:
            raise ValueError("non-clean reconciliation requires discrepancies")
        return self
