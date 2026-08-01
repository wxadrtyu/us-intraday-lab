import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from us_intraday_lab.backtest.costs import COST_SCENARIOS
from us_intraday_lab.contracts.backtests import CostModelIds
from us_intraday_lab.contracts.validation import ChronologicalSplit
from us_intraday_lab.factory.experiments import (
    BACKTEST_ENGINE_VERSION,
    VARIANT_GENERATOR_VERSION,
    ExperimentManifest,
    create_experiment_manifest,
)
from us_intraday_lab.factory.feature_catalog import FEATURE_TEMPLATE_CATALOG
from us_intraday_lab.factory.proposal import FixtureProposalProvider, proposal_hash

FIXTURE = Path(__file__).parents[2] / "fixtures" / "hypotheses" / "momentum_pullback.json"


def _split() -> ChronologicalSplit:
    return ChronologicalSplit(
        split_id="split-2026",
        train_sessions=(date(2026, 1, 2),),
        validation_sessions=(date(2026, 2, 2),),
        final_test_sessions=(date(2026, 3, 2),),
    )


def test_experiment_manifest_contains_complete_immutable_lineage() -> None:
    proposal = FixtureProposalProvider(FIXTURE).load()
    created_at = datetime(2026, 7, 26, tzinfo=UTC)
    manifest = create_experiment_manifest(
        proposal=proposal,
        dataset_id="dataset-accepted-1",
        calendar_version="XNYS@4.13.2",
        split_definition=_split(),
        code_revision="abc1234",
        created_at=created_at,
    )

    assert manifest.hypothesis_id == proposal.hypothesis_id
    assert manifest.proposal_hash == proposal_hash(proposal)
    assert manifest.catalog_version == FEATURE_TEMPLATE_CATALOG.version
    assert manifest.variant_generator_version == VARIANT_GENERATOR_VERSION
    assert manifest.backtest_engine_version == BACKTEST_ENGINE_VERSION
    assert manifest.cost_model_versions == CostModelIds(
        optimistic=COST_SCENARIOS["optimistic"].model_id,
        base=COST_SCENARIOS["base"].model_id,
        stress=COST_SCENARIOS["stress"].model_id,
    )
    assert ExperimentManifest.model_validate_json(manifest.model_dump_json()) == manifest
    with pytest.raises(ValidationError):
        manifest.dataset_id = "changed"


def test_experiment_id_is_derived_and_rejects_lineage_tampering() -> None:
    proposal = FixtureProposalProvider(FIXTURE).load()
    manifest = create_experiment_manifest(
        proposal=proposal,
        dataset_id="dataset-accepted-1",
        calendar_version="XNYS@4.13.2",
        split_definition=_split(),
        code_revision="abc1234",
        created_at=datetime(2026, 7, 26, tzinfo=UTC),
    )

    payload = manifest.model_dump(mode="json")
    payload["dataset_id"] = "changed"
    with pytest.raises(ValidationError, match="experiment_id"):
        ExperimentManifest.model_validate(payload)


def test_fixture_provider_validates_file_content_at_boundary(tmp_path: Path) -> None:
    unsafe = tmp_path / "unsafe.json"
    unsafe.write_text(json.dumps({"python": "print('unsafe')"}), encoding="utf-8")

    with pytest.raises(ValidationError):
        FixtureProposalProvider(unsafe).load()


def test_manifest_rejects_forged_proposal_and_nested_cost_ids() -> None:
    proposal = FixtureProposalProvider(FIXTURE).load()
    forged = proposal.model_copy(update={"hypothesis_id": "INVALID ID"})

    with pytest.raises(ValidationError):
        create_experiment_manifest(
            proposal=forged,
            dataset_id="dataset-accepted-1",
            calendar_version="XNYS@4.13.2",
            split_definition=_split(),
            code_revision="abc1234",
            created_at=datetime(2026, 7, 26, tzinfo=UTC),
        )

    manifest = create_experiment_manifest(
        proposal=proposal,
        dataset_id="dataset-accepted-1",
        calendar_version="XNYS@4.13.2",
        split_definition=_split(),
        code_revision="abc1234",
        created_at=datetime(2026, 7, 26, tzinfo=UTC),
    )
    forged_costs = manifest.cost_model_versions.model_copy(update={"base": ""})
    payload = manifest.model_dump(mode="python")
    payload["cost_model_versions"] = forged_costs
    with pytest.raises(ValidationError):
        ExperimentManifest.model_validate(payload)
