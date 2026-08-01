import math
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Literal, Self, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from us_intraday_lab.contracts.strategies import IndicatorName

ParameterName = Literal[
    "ema_spread_min",
    "rsi_entry",
    "volume_ratio_min",
    "stop_loss_bps",
    "take_profit_bps",
    "max_holding_minutes",
    "cooldown_minutes",
    "max_entries_per_session",
    "order_type",
    "sizing_preset",
]
ParameterValue = int | float | str


class _ClosedModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class ParameterRange(_ClosedModel):
    values: tuple[ParameterValue, ...]

    @field_validator("values", mode="before")
    @classmethod
    def validate_values(cls, value: object) -> tuple[ParameterValue, ...]:
        if type(value) not in {list, tuple}:
            raise ValueError("parameter values must be a JSON array")
        values: tuple[ParameterValue, ...] = tuple(
            cast(list[ParameterValue] | tuple[ParameterValue, ...], value)
        )
        if not 1 <= len(values) <= 20:
            raise ValueError("parameter values must contain between 1 and 20 items")
        for item in values:
            if type(item) not in {int, float, str}:
                raise ValueError("parameter values must be exact numeric or enum scalars")
            if type(item) is float and not math.isfinite(item):
                raise ValueError("numeric parameter values must be finite")
            if type(item) is str and not item:
                raise ValueError("enum parameter values must not be empty")
        if len(set(values)) != len(values):
            raise ValueError("parameter values must be unique")
        return values


class ProposalProvenance(_ClosedModel):
    source_type: Literal["fixture", "ai"] = "fixture"
    provider: str = Field(default="fixture", min_length=1, max_length=120)
    model: str | None = Field(default=None, min_length=1, max_length=200)
    prompt_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_source_metadata(self) -> Self:
        if self.source_type == "ai" and (self.model is None or self.prompt_sha256 is None):
            raise ValueError("AI proposals require provider, model, and prompt hash metadata")
        if self.source_type == "fixture" and (
            self.provider != "fixture" or self.model is not None or self.prompt_sha256 is not None
        ):
            raise ValueError("fixture proposals must use fixture provenance")
        return self


class HypothesisProposal(_ClosedModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    hypothesis_id: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9][a-z0-9-]*$")
    thesis: str = Field(min_length=1, max_length=2_000)
    entry_template: Literal["momentum_pullback"]
    exit_template: Literal["risk_managed"]
    indicators: tuple[IndicatorName, ...] = Field(min_length=1, max_length=9)
    parameter_ranges: Mapping[ParameterName, ParameterRange] = Field(min_length=1, max_length=10)
    symbols: tuple[Literal["SPY", "QQQ", "IWM"], ...]
    max_variants: int = Field(strict=True, ge=1, le=200)
    seed: int = Field(strict=True, ge=0, le=2**63 - 1)
    rationale: str = Field(min_length=1, max_length=2_000)
    provenance: ProposalProvenance = ProposalProvenance()

    @field_validator("parameter_ranges", mode="after")
    @classmethod
    def freeze_parameter_ranges(
        cls, value: Mapping[ParameterName, ParameterRange]
    ) -> Mapping[ParameterName, ParameterRange]:
        return MappingProxyType(dict(sorted(value.items())))

    @field_serializer("parameter_ranges")
    def serialize_parameter_ranges(
        self, value: Mapping[ParameterName, ParameterRange]
    ) -> dict[str, Any]:
        return {name: item.model_dump(mode="json") for name, item in value.items()}

    @model_validator(mode="after")
    def validate_catalog_and_scope(self) -> Self:
        if len(set(self.indicators)) != len(self.indicators):
            raise ValueError("indicators must be unique")
        if self.symbols != ("SPY", "QQQ", "IWM"):
            raise ValueError("symbols must be the ordered production trio SPY, QQQ, IWM")
        from us_intraday_lab.factory.feature_catalog import validate_parameter_ranges

        validate_parameter_ranges(
            entry_template=self.entry_template,
            exit_template=self.exit_template,
            indicators=self.indicators,
            parameter_ranges=self.parameter_ranges,
        )
        return self
