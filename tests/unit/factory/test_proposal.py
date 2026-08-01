from datetime import UTC, date, datetime
from types import MappingProxyType

import pytest
from pydantic import ValidationError

from us_intraday_lab.contracts.hypotheses import HypothesisProposal
from us_intraday_lab.contracts.registry import RegistryEvent
from us_intraday_lab.contracts.validation import (
    ChronologicalSplit,
    GateEvidence,
    GateResult,
    ValidationDecision,
    WalkForwardWindowResult,
)
from us_intraday_lab.factory.feature_catalog import FEATURE_TEMPLATE_CATALOG


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
    split = ChronologicalSplit(
        split_id="split-1",
        train_sessions=(date(2026, 1, 2), date(2026, 1, 3)),
        validation_sessions=(date(2026, 1, 4),),
        final_test_sessions=(date(2026, 1, 5),),
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
            train_sessions=(date(2026, 1, 5),),
            validation_sessions=(date(2026, 1, 4),),
            final_test_sessions=(date(2026, 1, 6),),
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
