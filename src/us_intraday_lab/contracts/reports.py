"""Versioned evidence-only paper reporting contracts."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from us_intraday_lab.contracts.paper import (
    BrokerAccount,
    BrokerOrder,
    PositionSnapshot,
    RiskDecision,
)


class DailyPaperReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    schema_version: Literal["1.0.0"] = "1.0.0"
    report_id: str = Field(min_length=1)
    paper_session_id: str = Field(min_length=1)
    session_date: date
    generated_at: datetime
    account: BrokerAccount
    final_positions: PositionSnapshot
    orders: tuple[BrokerOrder, ...]
    risk_decisions: tuple[RiskDecision, ...]
    incident_codes: tuple[str, ...]
    net_pnl: float

    @field_validator("generated_at")
    @classmethod
    def validate_generated_at(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("generated_at must be timezone-aware UTC")
        return value.astimezone(UTC)

    @field_validator("incident_codes")
    @classmethod
    def validate_incidents(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(re.fullmatch(r"[A-Z][A-Z0-9_]*", item) is None for item in value):
            raise ValueError("incident_codes must contain stable uppercase codes")
        return value
