import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

CostScenario = Literal["optimistic", "base", "stress"]
BacktestStatus = Literal["succeeded", "failed"]
BacktestFailureType = Literal[
    "strategy_validation",
    "dataset_validation",
    "feature_computation",
    "execution",
    "artifact_write",
    "internal",
]
_COST_SCENARIO_ORDER: tuple[CostScenario, ...] = ("optimistic", "base", "stress")


class _ClosedModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class CostModelIds(_ClosedModel):
    optimistic: str = Field(min_length=1)
    base: str = Field(min_length=1)
    stress: str = Field(min_length=1)


class _BacktestJobIdentity(_ClosedModel):
    schema_version: Literal["1.0.0"]
    strategy_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    engine_id: str = Field(min_length=1)
    calendar_id: str = Field(min_length=1)
    initial_cash: float = Field(strict=True, gt=0)
    closeout_buffer_minutes: int = Field(strict=True, ge=1, le=60)
    cost_model_ids: CostModelIds


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _derived_job_id(identity: _BacktestJobIdentity) -> str:
    encoded = _canonical_json(identity.model_dump(mode="json")).encode("utf-8")
    return "job-" + hashlib.sha256(encoded).hexdigest()


class BacktestJob(_ClosedModel):
    schema_version: Literal["1.0.0"]
    job_id: str = Field(pattern=r"^job-[0-9a-f]{64}$")
    strategy_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    engine_id: str = Field(min_length=1)
    calendar_id: str = Field(min_length=1)
    initial_cash: float = Field(strict=True, gt=0)
    closeout_buffer_minutes: int = Field(strict=True, ge=1, le=60)
    cost_model_ids: CostModelIds

    @model_validator(mode="before")
    @classmethod
    def derive_missing_job_id(cls, value: object) -> object:
        if not isinstance(value, Mapping) or "job_id" in value:
            return value
        payload = dict(value)
        identity = _BacktestJobIdentity.model_validate(payload)
        payload["job_id"] = _derived_job_id(identity)
        return payload

    @model_validator(mode="after")
    def validate_job_id(self) -> Self:
        identity = _BacktestJobIdentity.model_validate(self.model_dump(exclude={"job_id"}))
        if self.job_id != _derived_job_id(identity):
            raise ValueError("job_id does not match canonical BacktestJob identity")
        return self

    @classmethod
    def create(cls, **values: object) -> Self:
        """Validate inputs and derive the content-addressed job identifier."""
        return cls.model_validate(values)

    def canonical_json(self) -> str:
        """Return stable JSON used as the complete deterministic run identity."""
        return _canonical_json(self.model_dump(mode="json"))


class BacktestFailure(_ClosedModel):
    failure_type: BacktestFailureType
    message: str = Field(min_length=1)


class BacktestResult(_ClosedModel):
    schema_version: Literal["1.0.0"]
    run_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    status: BacktestStatus
    failure: BacktestFailure | None
    metrics_by_cost_scenario: Mapping[CostScenario, Mapping[str, float]]
    trades_uri: str = Field(min_length=1)
    events_uri: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("metrics_by_cost_scenario", mode="after")
    @classmethod
    def freeze_metrics(
        cls,
        value: Mapping[CostScenario, Mapping[str, float]],
    ) -> Mapping[CostScenario, Mapping[str, float]]:
        return MappingProxyType(
            {
                scenario: MappingProxyType(dict(sorted(value[scenario].items())))
                for scenario in _COST_SCENARIO_ORDER
                if scenario in value
            }
        )

    @field_serializer("metrics_by_cost_scenario")
    def serialize_metrics(
        self,
        value: Mapping[CostScenario, Mapping[str, float]],
    ) -> dict[CostScenario, dict[str, float]]:
        return {scenario: dict(metrics) for scenario, metrics in value.items()}

    @model_validator(mode="after")
    def validate_status_and_failure(self) -> Self:
        if self.status == "failed" and self.failure is None:
            raise ValueError("failed result requires a failure")
        if self.status == "failed" and self.metrics_by_cost_scenario:
            raise ValueError("failed result must not include partial metrics")
        if self.status == "succeeded" and self.failure is not None:
            raise ValueError("succeeded result must not include a failure")
        required_scenarios = {"optimistic", "base", "stress"}
        if (
            self.status == "succeeded"
            and self.metrics_by_cost_scenario.keys() != required_scenarios
        ):
            raise ValueError("succeeded result requires all three cost scenarios")
        return self


def failed_backtest_result(
    *,
    failure_type: BacktestFailureType,
    message: object,
    job_id: str | None = None,
    run_id: str | None = None,
    context: Mapping[str, Any] | None = None,
) -> BacktestResult:
    """Build a deterministic, complete failed result without partial metrics."""
    normalized_message = str(message).strip() or "unspecified failure"
    identity = {
        "context": dict(context or {}),
        "failure_type": failure_type,
        "message": normalized_message,
    }
    digest = hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()
    effective_job_id = job_id or f"job-failed-{digest}"
    effective_run_id = run_id or f"run-failed-{digest}"
    relative_root = Path("artifacts") / "backtests" / effective_run_id
    content_sha256 = hashlib.sha256(
        _canonical_json(
            {
                **identity,
                "job_id": effective_job_id,
                "run_id": effective_run_id,
            }
        ).encode("utf-8")
    ).hexdigest()
    return BacktestResult(
        schema_version="1.0.0",
        run_id=effective_run_id,
        job_id=effective_job_id,
        status="failed",
        failure=BacktestFailure(
            failure_type=failure_type,
            message=normalized_message,
        ),
        metrics_by_cost_scenario={},
        trades_uri=(relative_root / "trades.jsonl").as_posix(),
        events_uri=(relative_root / "events.jsonl").as_posix(),
        content_sha256=content_sha256,
    )
