from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class _ClosedModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class CostModelIds(_ClosedModel):
    optimistic: str = Field(min_length=1)
    base: str = Field(min_length=1)
    stress: str = Field(min_length=1)


class BacktestJob(_ClosedModel):
    schema_version: Literal["1.0.0"]
    job_id: str = Field(min_length=1)
    strategy_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    engine_id: str = Field(min_length=1)
    calendar_id: str = Field(min_length=1)
    cost_model_ids: CostModelIds


class BacktestFailure(_ClosedModel):
    failure_type: BacktestFailureType
    message: str = Field(min_length=1)


class BacktestResult(_ClosedModel):
    schema_version: Literal["1.0.0"]
    run_id: str = Field(min_length=1)
    job_id: str = Field(min_length=1)
    status: BacktestStatus
    failure: BacktestFailure | None
    metrics_by_cost_scenario: dict[CostScenario, dict[str, float]]
    trades_uri: str = Field(min_length=1)
    events_uri: str = Field(min_length=1)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

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
