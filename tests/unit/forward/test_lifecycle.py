import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from us_intraday_lab.contracts.strategies import (
    ComparisonCondition,
    RiskDefinition,
    StrategyDefinition,
)
from us_intraday_lab.contracts.validation import GateEvidence, GateResult, ValidationDecision
from us_intraday_lab.forward.eligibility import BrokerConfirmedTrade, ForwardEvidence
from us_intraday_lab.forward.evaluator import (
    EvaluationInput,
    evaluate_and_promote,
    evaluate_forward,
)
from us_intraday_lab.forward.lifecycle import explicit_transition
from us_intraday_lab.registry.lifecycle import LifecycleError
from us_intraday_lab.registry.store import RegistryStore

NOW = datetime(2026, 8, 3, 3, 0, tzinfo=UTC)


def _definition(strategy_id: str) -> StrategyDefinition:
    return StrategyDefinition(
        strategy_id=strategy_id,
        dsl_version="1.0.0",
        symbols=("SPY", "QQQ", "IWM"),
        signal_bar_size="15min",
        entry=ComparisonCondition(indicator="return_3", op="gt", value=0.01),
        exit=ComparisonCondition(indicator="return_1", op="lt", value=0.0),
        risk=RiskDefinition(
            stop_loss_bps=50,
            take_profit_bps=100,
            max_holding_minutes=60,
            cooldown_minutes=15,
            max_entries_per_session=2,
            sizing_preset="equal_cash_conservative",
        ),
        order_type="market",
    )


def _register_observing(store: RegistryStore, strategy_id: str) -> None:
    definition = _definition(strategy_id)
    payload = json.dumps(
        definition.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    store.register_strategy(
        definition,
        content_sha256=hashlib.sha256(payload.encode()).hexdigest(),
        idempotency_key=f"register:{strategy_id}",
        actor="factory",
        occurred_at=NOW,
    )
    evidence = GateEvidence(
        evidence_id=f"backtest-{strategy_id}",
        metric_name="return",
        source_refs=("run:a",),
        values={"return": 0.1},
    )
    decision = ValidationDecision(
        decision_id=f"decision-{strategy_id}",
        strategy_id=strategy_id,
        split_id="split-a",
        decision="PROMOTE_TO_PAPER_SHADOW",
        gate_results=(
            GateResult(
                reason_code="RETURN_GATE",
                threshold=0.0,
                observed=0.1,
                passed=True,
                evidence=evidence,
            ),
        ),
        decided_at=NOW,
    )
    store.record_validation_decision(decision)
    store.transition_strategy(
        strategy_id,
        to_state="candidate",
        idempotency_key=f"candidate:{strategy_id}",
        actor="validation",
        reason_code="VALIDATION_COMPLETE",
        immutable_refs={"decision_id": decision.decision_id},
        occurred_at=NOW,
    )
    store.transition_strategy(
        strategy_id,
        to_state="paper_shadow",
        idempotency_key=f"shadow:{strategy_id}",
        actor="validation",
        reason_code="SELECTED_SURVIVOR",
        immutable_refs={"decision_id": decision.decision_id},
        occurred_at=NOW,
    )
    store.transition_strategy(
        strategy_id,
        to_state="paper_observing",
        idempotency_key=f"observe:{strategy_id}",
        actor="paper",
        reason_code="PAPER_FORWARD_STARTED",
        immutable_refs={"paper_config_id": "paper-v1"},
        occurred_at=NOW,
    )


def _forward(strategy_id: str, *, trades: int = 50) -> ForwardEvidence:
    days = tuple(date(2026, 1, 2) + timedelta(days=index) for index in range(30))
    return ForwardEvidence(
        evidence_id=f"forward-{strategy_id}",
        strategy_id=strategy_id,
        completed_days=days,
        closed_trades=tuple(
            BrokerConfirmedTrade(
                trade_id=f"trade-{strategy_id}-{index}",
                strategy_id=strategy_id,
                session_date=days[index % 30],
                symbol=("SPY", "QQQ", "IWM")[index % 3],
                net_return=0.001,
                net_pnl=5.0,
                fees_bps=0.01,
                slippage_bps=0.25,
            )
            for index in range(trades)
        ),
        unresolved_reconciliations=0,
        unresolved_overnight_incidents=0,
        data_completeness=1.0,
        execution_quality=1.0,
        expected_net_return=0.05,
    )


def test_forward_lifecycle_and_explicit_evidence_linked_demotion(tmp_path: Path) -> None:
    store = RegistryStore(tmp_path / "registry.sqlite3")
    _register_observing(store, "strategy-a")
    evaluation = evaluate_and_promote(
        store,
        (EvaluationInput(_forward("strategy-a"), "paper_observing"),),
        occurred_at=NOW,
    )
    assert evaluation.rankings[0].strategy_id == "strategy-a"
    assert store.get_current_state("strategy-a") == "paper_ranked"
    ranked_event = store.list_events("strategy-a")[-1]
    assert "component_values" in ranked_event.immutable_refs
    assert "ranking_weights" in ranked_event.immutable_refs
    explicit_transition(
        store,
        "strategy-a",
        to_state="leader",
        evidence_id="forward-strategy-a",
        reason_code="TOP_FORWARD_RANK",
        idempotency_key="leader:strategy-a",
        occurred_at=NOW,
    )
    paused = explicit_transition(
        store,
        "strategy-a",
        to_state="paused",
        evidence_id="forward-strategy-a",
        reason_code="EXPLICIT_RANK_DEMOTION",
        idempotency_key="pause:strategy-a",
        occurred_at=NOW,
    )
    assert paused.immutable_refs["forward_evidence_id"] == "forward-strategy-a"
    assert store.get_current_state("strategy-a") == "paused"
    assert len(store.list_events("strategy-a")) == 7


def test_hard_gate_failure_never_reaches_ranking_or_registry_write(tmp_path: Path) -> None:
    store = RegistryStore(tmp_path / "registry.sqlite3")
    _register_observing(store, "strategy-a")
    before = store.list_events("strategy-a")
    result = evaluate_and_promote(
        store,
        (EvaluationInput(_forward("strategy-a", trades=49), "paper_observing"),),
        occurred_at=NOW,
    )
    assert not result.decisions[0].eligible
    assert result.rankings == ()
    assert store.list_events("strategy-a") == before


def test_capacity_is_enforced_inside_registry_transaction(tmp_path: Path) -> None:
    store = RegistryStore(tmp_path / "registry.sqlite3")
    for index in range(6):
        _register_observing(store, f"strategy-{index}")
    for index in range(5):
        evaluate_and_promote(
            store,
            (EvaluationInput(_forward(f"strategy-{index}"), "paper_observing"),),
            occurred_at=NOW,
        )
    before = store.list_events("strategy-5")
    with pytest.raises(LifecycleError, match="REGISTRY_STATE_CAPACITY_EXCEEDED"):
        evaluate_and_promote(
            store,
            (EvaluationInput(_forward("strategy-5"), "paper_observing"),),
            occurred_at=NOW,
        )
    assert store.get_current_state("strategy-5") == "paper_observing"
    assert store.list_events("strategy-5") == before


def test_evaluator_ranks_only_eligible_inputs() -> None:
    result = evaluate_forward(
        (
            EvaluationInput(_forward("eligible"), "paper_observing"),
            EvaluationInput(_forward("too-young", trades=49), "paper_observing"),
        )
    )
    assert tuple(item.strategy_id for item in result.rankings) == ("eligible",)
