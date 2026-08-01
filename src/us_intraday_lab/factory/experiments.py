import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from us_intraday_lab.backtest.costs import COST_SCENARIOS
from us_intraday_lab.backtest.engine import ENGINE_ID
from us_intraday_lab.contracts.backtests import CostModelIds
from us_intraday_lab.contracts.hypotheses import HypothesisProposal
from us_intraday_lab.contracts.validation import ChronologicalSplit
from us_intraday_lab.factory.feature_catalog import FEATURE_TEMPLATE_CATALOG
from us_intraday_lab.factory.proposal import proposal_hash
from us_intraday_lab.factory.variants import VARIANT_GENERATOR_VERSION

BACKTEST_ENGINE_VERSION = ENGINE_ID


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


class _ExperimentIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["1.0.0"]
    hypothesis_id: str
    proposal_hash: str
    catalog_version: str
    variant_generator_version: str
    dataset_id: str
    backtest_engine_version: str
    calendar_version: str
    cost_model_versions: CostModelIds
    split_definition: ChronologicalSplit
    code_revision: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    created_at: datetime


def _experiment_id(identity: _ExperimentIdentity) -> str:
    digest = hashlib.sha256(
        _canonical_json(identity.model_dump(mode="json")).encode("utf-8")
    ).hexdigest()
    return f"experiment-{digest}"


class ExperimentManifest(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        allow_inf_nan=False,
        revalidate_instances="always",
    )

    schema_version: Literal["1.0.0"]
    experiment_id: str = Field(pattern=r"^experiment-[0-9a-f]{64}$")
    hypothesis_id: str = Field(min_length=1)
    proposal_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_version: str = Field(min_length=1)
    variant_generator_version: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1)
    backtest_engine_version: str = Field(min_length=1)
    calendar_version: str = Field(min_length=1)
    cost_model_versions: CostModelIds
    split_definition: ChronologicalSplit
    code_revision: str = Field(pattern=r"^[0-9a-f]{7,64}$")
    created_at: datetime

    @field_validator("created_at")
    @classmethod
    def validate_utc(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("created_at must be timezone-aware UTC")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        identity = _ExperimentIdentity.model_validate(self.model_dump(exclude={"experiment_id"}))
        if self.experiment_id != _experiment_id(identity):
            raise ValueError("experiment_id does not match immutable lineage")
        return self


def create_experiment_manifest(
    *,
    proposal: HypothesisProposal,
    dataset_id: str,
    calendar_version: str,
    split_definition: ChronologicalSplit,
    code_revision: str,
    created_at: datetime,
) -> ExperimentManifest:
    identity = _ExperimentIdentity(
        schema_version="1.0.0",
        hypothesis_id=proposal.hypothesis_id,
        proposal_hash=proposal_hash(proposal),
        catalog_version=FEATURE_TEMPLATE_CATALOG.version,
        variant_generator_version=VARIANT_GENERATOR_VERSION,
        dataset_id=dataset_id,
        backtest_engine_version=BACKTEST_ENGINE_VERSION,
        calendar_version=calendar_version,
        cost_model_versions=CostModelIds(
            optimistic=COST_SCENARIOS["optimistic"].model_id,
            base=COST_SCENARIOS["base"].model_id,
            stress=COST_SCENARIOS["stress"].model_id,
        ),
        split_definition=split_definition,
        code_revision=code_revision,
        created_at=created_at,
    )
    return ExperimentManifest(
        experiment_id=_experiment_id(identity),
        **identity.model_dump(),
    )
