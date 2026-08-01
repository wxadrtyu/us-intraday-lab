from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
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

RegistryState = Literal[
    "generated",
    "backtested",
    "validated",
    "candidate",
    "paper_shadow",
    "rejected",
    "paused",
    "retired",
]


class RegistryEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    schema_version: Literal["1.0.0"] = "1.0.0"
    event_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    from_state: RegistryState | None
    to_state: RegistryState
    actor: str = Field(min_length=1)
    reason_code: str = Field(min_length=1, pattern=r"^[A-Z][A-Z0-9_]*$")
    immutable_refs: Mapping[str, str]
    occurred_at: datetime

    @field_validator("immutable_refs", mode="after")
    @classmethod
    def freeze_refs(cls, value: Mapping[str, str]) -> Mapping[str, str]:
        if not value or any(not key or not item for key, item in value.items()):
            raise ValueError("immutable_refs must contain non-empty keys and values")
        return MappingProxyType(dict(sorted(value.items())))

    @field_serializer("immutable_refs")
    def serialize_refs(self, value: Mapping[str, str]) -> dict[str, str]:
        return dict(value)

    @field_validator("occurred_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("occurred_at must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def reject_noop_transition(self) -> Self:
        if self.from_state == self.to_state:
            raise ValueError("registry transition must change state")
        return self
