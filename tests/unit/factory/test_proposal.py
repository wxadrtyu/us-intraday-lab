from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import MappingProxyType

import pytest
from pydantic import ValidationError

from us_intraday_lab.contracts.hypotheses import HypothesisProposal, ProposalProvenance
from us_intraday_lab.contracts.registry import RegistryEvent
from us_intraday_lab.contracts.validation import (
    ChronologicalSplit,
    GateEvidence,
    GateResult,
    ValidationDecision,
    WalkForwardWindowResult,
)
from us_intraday_lab.factory.feature_catalog import FEATURE_TEMPLATE_CATALOG
from us_intraday_lab.factory.proposal import (
    MAX_FIXTURE_BYTES,
    FixtureProposalProvider,
    proposal_hash,
)


def _proposal_payload() -> dict[str, object]:
    return {
        "hypothesis_id": "intraday-momentum-pullback",
        "thesis": "Trend continuation after a shallow pullback",
        "entry_template": "momentum_pullback",
        "exit_template": "risk_managed",
        "indicators": ["ema_spread", "rsi", "volume_ratio"],
        "parameter_ranges": {
            "rsi_entry": {"values": [35.0, 40.0, 45.0]},
            "stop_loss_bps": {"values": [25, 35, 45]},
        },
        "symbols": ["SPY", "QQQ", "IWM"],
        "max_variants": 60,
        "seed": 20260726,
        "rationale": "Price and volume confirmation may reduce false entries.",
    }


def test_proposal_contains_bounded_data_only_search_space() -> None:
    proposal = HypothesisProposal.model_validate(_proposal_payload())

    assert proposal.max_variants == 60
    assert isinstance(proposal.parameter_ranges, MappingProxyType)
    with pytest.raises(TypeError):
        proposal.parameter_ranges["rsi_entry"] = proposal.parameter_ranges["rsi_entry"]


@pytest.mark.parametrize(
    "change",
    [
        {"python": "print('run me')"},
        {"entry_template": "freeform"},
        {"indicators": ["ema_spread", "custom_alpha"]},
        {"indicators": ["return_1"]},
        {"symbols": ["SPY", "QQQ", "BTC"]},
        {"max_variants": 201},
        {"parameter_ranges": {"unknown": {"values": [1]}}},
        {"parameter_ranges": {"rsi_entry": {"values": []}}},
        {"parameter_ranges": {"rsi_entry": {"values": [True]}}},
    ],
)
def test_proposal_rejects_unsafe_or_unbounded_fields(change: dict[str, object]) -> None:
    payload = {**_proposal_payload(), **change}

    with pytest.raises(ValidationError):
        HypothesisProposal.model_validate(payload)


def test_validation_contracts_are_chronological_closed_and_frozen() -> None:
    sessions = tuple(date(2026, 1, 2) + timedelta(days=index) for index in range(10))
    split = ChronologicalSplit(
        split_id="split-1",
        train_sessions=sessions[:7],
        validation_sessions=sessions[7:9],
        final_test_sessions=sessions[9:],
    )
    evidence = GateEvidence(
        evidence_id="evidence-1",
        metric_name="base_net_return",
        source_refs=("run-1",),
        values={"base": 0.02, "stress_1_5x": 0.005},
    )
    gate = GateResult(
        reason_code="POSITIVE_AFTER_COSTS",
        threshold=0.0,
        observed=0.005,
        passed=True,
        evidence=evidence,
    )
    decision = ValidationDecision(
        decision_id="decision-1",
        strategy_id="strategy-1",
        split_id=split.split_id,
        decision="PROMOTE_TO_PAPER_SHADOW",
        gate_results=(gate,),
        decided_at=datetime(2026, 7, 26, tzinfo=UTC),
    )

    assert decision.gate_results[0].evidence.values["base"] == 0.02
    with pytest.raises(ValidationError):
        decision.decision = "REJECT"
    with pytest.raises(ValidationError):
        ChronologicalSplit(
            split_id="bad",
            train_sessions=(*sessions[:6], sessions[7]),
            validation_sessions=(sessions[6], sessions[8]),
            final_test_sessions=sessions[9:],
        )

    window = WalkForwardWindowResult(
        window_id="window-1",
        strategy_id="strategy-1",
        train_start=date(2026, 1, 2),
        train_end=date(2026, 2, 1),
        validation_start=date(2026, 2, 2),
        validation_end=date(2026, 2, 28),
        metrics_by_cost_scenario={"base": {"net_return": 0.01}},
    )
    with pytest.raises(TypeError):
        window.metrics_by_cost_scenario["base"]["net_return"] = 1.0
    assert WalkForwardWindowResult.model_validate_json(window.model_dump_json()) == window


def test_registry_event_is_append_only_data_with_immutable_references() -> None:
    event = RegistryEvent(
        event_id="event-1",
        strategy_id="strategy-1",
        from_state="validated",
        to_state="paper_shadow",
        actor="validation-service",
        reason_code="ALL_HARD_GATES_PASSED",
        immutable_refs={"decision_id": "decision-1", "dataset_id": "dataset-1"},
        occurred_at=datetime(2026, 7, 26, tzinfo=UTC),
    )

    assert isinstance(event.immutable_refs, MappingProxyType)
    with pytest.raises(TypeError):
        event.immutable_refs["dataset_id"] = "changed"


@pytest.mark.parametrize("forged_passed", ["yes", "true", 1, 1.0])
def test_promotion_rejects_coerced_or_forged_gate_passed_values(
    forged_passed: object,
) -> None:
    evidence = GateEvidence(
        evidence_id="evidence-1",
        metric_name="base_net_return",
        source_refs=("run-1",),
        values={"base": 0.02},
    )
    with pytest.raises(ValidationError):
        GateResult.model_validate(
            {
                "reason_code": "POSITIVE_AFTER_COSTS",
                "threshold": 0.0,
                "observed": 0.02,
                "passed": forged_passed,
                "evidence": evidence,
            }
        )

    valid = GateResult(
        reason_code="POSITIVE_AFTER_COSTS",
        threshold=0.0,
        observed=0.02,
        passed=True,
        evidence=evidence,
    )
    forged = valid.model_copy(update={"passed": forged_passed})
    with pytest.raises(ValidationError):
        ValidationDecision(
            decision_id="decision-forged",
            strategy_id="strategy-1",
            split_id="split-1",
            decision="PROMOTE_TO_PAPER_SHADOW",
            gate_results=(forged,),
            decided_at=datetime(2026, 7, 26, tzinfo=UTC),
        )


def test_feature_template_catalog_is_immutable_and_declares_parameter_ownership() -> None:
    parameter = FEATURE_TEMPLATE_CATALOG.entry_templates["momentum_pullback"].parameters[
        "rsi_entry"
    ]

    assert parameter.affects == "entry"
    assert parameter.value_type == "float"
    assert parameter.minimum == 0.0
    assert parameter.maximum == 100.0
    with pytest.raises(TypeError):
        FEATURE_TEMPLATE_CATALOG.entry_templates["other"] = (
            FEATURE_TEMPLATE_CATALOG.entry_templates["momentum_pullback"]
        )


def test_ai_proposal_requires_provider_model_and_prompt_lineage() -> None:
    payload = _proposal_payload()
    payload["provenance"] = {"source_type": "ai", "provider": "future-provider"}

    with pytest.raises(ValidationError):
        HypothesisProposal.model_validate(payload)

    payload["provenance"] = {
        "source_type": "ai",
        "provider": "future-provider",
        "model": "future-model",
        "prompt_sha256": "a" * 64,
    }
    proposal = HypothesisProposal.model_validate(payload)
    assert proposal.provenance.model == "future-model"


@pytest.mark.parametrize("max_variants", [1, 2])
def test_proposal_budget_must_fit_robustness_neighborhood(
    max_variants: int,
) -> None:
    payload = _proposal_payload()
    payload["max_variants"] = max_variants

    with pytest.raises(ValidationError, match="greater than or equal to 3"):
        HypothesisProposal.model_validate(payload)


def test_singleton_search_space_is_rejected_without_robustness_neighbors() -> None:
    payload = _proposal_payload()
    payload["parameter_ranges"] = {
        "rsi_entry": {"values": [40.0]},
        "stop_loss_bps": {"values": [35]},
    }
    payload["max_variants"] = 3

    with pytest.raises(ValidationError, match="three robustness neighbors"):
        HypothesisProposal.model_validate(payload)


def test_proposal_hash_rejects_model_copy_forgery() -> None:
    proposal = HypothesisProposal.model_validate(_proposal_payload())
    forged_provenance = ProposalProvenance().model_copy(
        update={"source_type": "ai", "provider": "fixture"}
    )

    with pytest.raises(ValidationError):
        proposal_hash(proposal.model_copy(update={"provenance": forged_provenance}))
    with pytest.raises(ValidationError):
        proposal_hash(proposal.model_copy(update={"max_variants": True}))

    forged_range = proposal.parameter_ranges["stop_loss_bps"].model_copy(
        update={"values": (True, 35, 45)}
    )
    forged_ranges = dict(proposal.parameter_ranges)
    forged_ranges["stop_loss_bps"] = forged_range
    with pytest.raises(ValidationError):
        proposal_hash(proposal.model_copy(update={"parameter_ranges": forged_ranges}))


def test_fixture_provider_enforces_read_bound_on_open_handle(tmp_path: Path) -> None:
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (MAX_FIXTURE_BYTES + 1))

    with pytest.raises(ValueError, match="bounded read size"):
        FixtureProposalProvider(oversized).load()
