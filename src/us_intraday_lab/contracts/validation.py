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

from us_intraday_lab.contracts.backtests import CostScenario

_CHRONOLOGICAL_WEIGHTS = (7, 2, 1)


def chronological_split_counts(total: int) -> tuple[int, int, int]:
    """Allocate sessions with a deterministic largest-remainder 70/20/10 rule."""
    if type(total) is not int:
        raise TypeError("total must be an exact integer")
    if total < 10:
        raise ValueError("total must contain at least 10 sessions")
    counts = [total * weight // 10 for weight in _CHRONOLOGICAL_WEIGHTS]
    remainders = [total * weight % 10 for weight in _CHRONOLOGICAL_WEIGHTS]
    remaining = total - sum(counts)
    order = sorted(
        range(len(remainders)),
        key=lambda index: (-remainders[index], index),
    )
    for index in order[:remaining]:
        counts[index] += 1
    return counts[0], counts[1], counts[2]


class _ClosedModel(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        allow_inf_nan=False,
        revalidate_instances="always",
    )


class ChronologicalSplit(_ClosedModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    split_id: str = Field(min_length=1)
    allocation_method: Literal["largest_remainder_70_20_10"] = "largest_remainder_70_20_10"
    train_sessions: tuple[date, ...] = Field(min_length=1, max_length=100_000)
    validation_sessions: tuple[date, ...] = Field(min_length=1, max_length=100_000)
    final_test_sessions: tuple[date, ...] = Field(min_length=1, max_length=100_000)

    @model_validator(mode="after")
    def validate_chronology(self) -> Self:
        groups = (self.train_sessions, self.validation_sessions, self.final_test_sessions)
        if any(tuple(sorted(group)) != group or len(set(group)) != len(group) for group in groups):
            raise ValueError("split sessions must be sorted and unique")
        if not (
            self.train_sessions[-1]
            < self.validation_sessions[0]
            <= self.validation_sessions[-1]
            < self.final_test_sessions[0]
        ):
            raise ValueError("split sessions must be strictly chronological and disjoint")
        observed_counts = tuple(len(group) for group in groups)
        total = sum(observed_counts)
        if total > 100_000:
            raise ValueError("split cannot exceed 100000 sessions")
        if observed_counts != chronological_split_counts(total):
            raise ValueError("split sessions must use deterministic 70/20/10 allocation")
        return self


class WalkForwardWindowResult(_ClosedModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    window_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    train_start: date
    train_end: date
    validation_start: date
    validation_end: date
    metrics_by_cost_scenario: Mapping[CostScenario, Mapping[str, float]]

    @field_validator("metrics_by_cost_scenario", mode="after")
    @classmethod
    def freeze_metrics(
        cls, value: Mapping[CostScenario, Mapping[str, float]]
    ) -> Mapping[CostScenario, Mapping[str, float]]:
        return MappingProxyType(
            {
                scenario: MappingProxyType(dict(sorted(metrics.items())))
                for scenario, metrics in sorted(value.items())
            }
        )

    @field_serializer("metrics_by_cost_scenario")
    def serialize_metrics(
        self, value: Mapping[CostScenario, Mapping[str, float]]
    ) -> dict[str, dict[str, float]]:
        return {scenario: dict(metrics) for scenario, metrics in value.items()}

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if not self.train_start <= self.train_end < self.validation_start <= self.validation_end:
            raise ValueError("walk-forward window must be chronological")
        return self


class GateEvidence(_ClosedModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    evidence_id: str = Field(min_length=1)
    metric_name: str = Field(min_length=1)
    source_refs: tuple[str, ...] = Field(min_length=1)
    values: Mapping[str, float]

    @field_validator("values", mode="after")
    @classmethod
    def freeze_values(cls, value: Mapping[str, float]) -> Mapping[str, float]:
        return MappingProxyType(dict(sorted(value.items())))

    @field_serializer("values")
    def serialize_values(self, value: Mapping[str, float]) -> dict[str, float]:
        return dict(value)


GateScalar = float | int | bool | str


class GateResult(_ClosedModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    reason_code: str = Field(min_length=1, pattern=r"^[A-Z][A-Z0-9_]*$")
    threshold: GateScalar
    observed: GateScalar
    passed: bool = Field(strict=True)
    evidence: GateEvidence


class ValidationDecision(_ClosedModel):
    schema_version: Literal["1.0.0"] = "1.0.0"
    decision_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    split_id: str = Field(min_length=1)
    decision: Literal["REJECT", "PROMOTE_TO_PAPER_SHADOW"]
    gate_results: tuple[GateResult, ...] = Field(min_length=1)
    decided_at: datetime

    @field_validator("decided_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("decided_at must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        all_passed = all(result.passed for result in self.gate_results)
        if self.decision == "PROMOTE_TO_PAPER_SHADOW" and not all_passed:
            raise ValueError("promotion requires every hard gate to pass")
        if self.decision == "REJECT" and all_passed:
            raise ValueError("rejection requires at least one failed hard gate")
        return self
