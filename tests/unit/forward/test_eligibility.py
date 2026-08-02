from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from us_intraday_lab.forward.eligibility import (
    BrokerConfirmedTrade,
    ForwardEvidence,
    evaluate_eligibility,
)


def evidence(*, days: int = 30, trades: int = 50, **changes: object) -> ForwardEvidence:
    completed = tuple(date(2026, 1, 2) + timedelta(days=index) for index in range(days))
    values: dict[str, object] = {
        "evidence_id": "forward-a",
        "strategy_id": "strategy-a",
        "completed_days": completed,
        "closed_trades": tuple(
            BrokerConfirmedTrade(
                trade_id=f"trade-{index}",
                strategy_id="strategy-a",
                session_date=completed[index % days],
                symbol=("SPY", "QQQ", "IWM")[index % 3],
                net_return=0.001,
                net_pnl=10.0,
                fees_bps=0.01,
                slippage_bps=0.5,
            )
            for index in range(trades)
        ),
        "unresolved_reconciliations": 0,
        "unresolved_overnight_incidents": 0,
        "data_completeness": 0.995,
        "execution_quality": 0.98,
        "expected_net_return": 0.04,
    }
    values.update(changes)
    return ForwardEvidence.model_validate(values)


def test_exact_thresholds_with_broker_fills_are_eligible() -> None:
    decision = evaluate_eligibility(
        evidence(), lifecycle_state="paper_observing", capacity_available=True
    )

    assert decision.eligible
    assert all(gate.passed for gate in decision.gates)


@pytest.mark.parametrize(
    ("change", "state", "capacity", "reason"),
    [
        ({"days": 29}, "paper_observing", True, "MIN_COMPLETED_PAPER_DAYS"),
        (
            {"unresolved_reconciliations": 1},
            "paper_observing",
            True,
            "NO_UNRESOLVED_RECONCILIATION",
        ),
        (
            {"unresolved_overnight_incidents": 1},
            "paper_observing",
            True,
            "NO_UNRESOLVED_OVERNIGHT_RISK",
        ),
        ({"data_completeness": 0.98}, "paper_observing", True, "MIN_DATA_COMPLETENESS"),
        ({}, "paper_shadow", True, "OBSERVING_LIFECYCLE_REQUIRED"),
        ({}, "paper_observing", False, "RANKED_CAPACITY_AVAILABLE"),
    ],
)
def test_any_hard_gate_failure_blocks_ranking(
    change: dict[str, object], state: str, capacity: bool, reason: str
) -> None:
    item = evidence(**change)
    decision = evaluate_eligibility(item, lifecycle_state=state, capacity_available=capacity)  # type: ignore[arg-type]

    assert not decision.eligible
    assert reason in {gate.reason_code for gate in decision.gates if not gate.passed}


def test_non_broker_fill_cannot_enter_forward_evidence() -> None:
    with pytest.raises(ValidationError, match="broker_confirmed_fill"):
        BrokerConfirmedTrade(
            trade_id="shadow-trade",
            strategy_id="strategy-a",
            session_date=date(2026, 1, 2),
            symbol="SPY",
            net_return=0.1,
            net_pnl=100.0,
            fees_bps=0.0,
            slippage_bps=0.0,
            source="backtest",  # type: ignore[arg-type]
        )
