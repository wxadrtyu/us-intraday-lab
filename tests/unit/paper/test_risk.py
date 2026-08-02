from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from us_intraday_lab.contracts.orders import OrderIntent
from us_intraday_lab.paper.risk import RiskContext, evaluate_entry_risk
from us_intraday_lab.paper.sizing import SizingResult

NOW = datetime(2026, 7, 2, 16, 0, tzinfo=UTC)


def _intent(**updates: object) -> OrderIntent:
    values: dict[str, object] = {
        "schema_version": "1.0.0",
        "run_id": "paper-session-1",
        "strategy_id": "strategy-1",
        "symbol": "SPY",
        "session": date(2026, 7, 2),
        "side": "buy",
        "order_type": "market",
        "quantity": 10,
        "signal_time": NOW - timedelta(minutes=1),
        "eligible_time": NOW,
        "reason_code": "entry_signal",
        "idempotency_key": "intent-1",
    }
    values.update(updates)
    return OrderIntent.model_validate(values)


def _context(**updates: object) -> RiskContext:
    values: dict[str, object] = {
        "intent": _intent(),
        "decided_at": NOW,
        "regular_open": NOW - timedelta(hours=2),
        "regular_close": NOW + timedelta(hours=4),
        "closeout_buffer": timedelta(minutes=5),
        "feed_observed_at": NOW - timedelta(seconds=10),
        "broker_clock_observed_at": NOW - timedelta(seconds=2),
        "max_feed_age": timedelta(seconds=90),
        "max_broker_clock_age": timedelta(seconds=5),
        "reconciliation_status": "clean",
        "storage_circuit_open": False,
        "account_position_count": 0,
        "strategy_entry_count": 0,
        "strategy_state": "paper_shadow",
        "available_cash": 10_000.0,
        "account_multiplier": 1,
        "sizing": SizingResult(
            approved=True,
            reason_code="SIZED_INTEGER_POSITION",
            quantity=10,
            required_cash=1_000.0,
            risk_cash=50.0,
            binding_cap="risk",
        ),
        "daily_loss": 0.0,
        "daily_loss_limit": 500.0,
        "account_loss": 0.0,
        "account_loss_limit": 1_000.0,
        "strategy_loss": 0.0,
        "strategy_loss_limit": 250.0,
        "duplicate_intent": False,
        "conflicting_intent": False,
    }
    values.update(updates)
    return RiskContext(**values)


@pytest.mark.parametrize(
    ("updates", "reason_code", "observed_key"),
    [
        ({"intent": _intent(symbol="AAPL")}, "SYMBOL_NOT_ALLOWED", "symbol"),
        ({"decided_at": NOW - timedelta(hours=3)}, "OUTSIDE_REGULAR_HOURS", "decided_at"),
        (
            {
                "decided_at": NOW + timedelta(hours=3, minutes=56),
                "feed_observed_at": NOW + timedelta(hours=3, minutes=56),
                "broker_clock_observed_at": NOW + timedelta(hours=3, minutes=56),
            },
            "CLOSEOUT_BUFFER_ACTIVE",
            "closeout_at",
        ),
        ({"feed_observed_at": NOW - timedelta(minutes=2)}, "FEED_STALE", "feed_age_seconds"),
        (
            {"broker_clock_observed_at": NOW - timedelta(seconds=6)},
            "BROKER_CLOCK_STALE",
            "broker_clock_age_seconds",
        ),
        ({"reconciliation_status": "blocked"}, "RECONCILIATION_NOT_CLEAN", "reconciliation_status"),
        ({"storage_circuit_open": True}, "STORAGE_CIRCUIT_OPEN", "storage_circuit_open"),
        ({"account_position_count": 3}, "ACCOUNT_POSITION_LIMIT", "account_position_count"),
        ({"strategy_entry_count": 3}, "STRATEGY_ENTRY_LIMIT", "strategy_entry_count"),
        ({"strategy_state": "paused"}, "STRATEGY_NOT_ENABLED", "strategy_state"),
        ({"intent": _intent(side="sell", reason_code="exit_signal")}, "LONG_ONLY_ENTRY_REQUIRED", "side"),
        ({"available_cash": -1.0}, "NEGATIVE_CASH", "available_cash"),
        (
            {"sizing": replace(_context().sizing, required_cash=10_001.0)},
            "MARGIN_OR_LEVERAGE_REQUIRED",
            "required_cash",
        ),
        (
            {
                "sizing": SizingResult(
                    approved=False,
                    reason_code="NO_FEASIBLE_INTEGER_POSITION",
                    quantity=0,
                    required_cash=0.0,
                    risk_cash=0.0,
                    binding_cap="cash",
                )
            },
            "NO_FEASIBLE_INTEGER_POSITION",
            "sizing_reason",
        ),
        (
            {"sizing": replace(_context().sizing, quantity=9)},
            "QUANTITY_EXCEEDS_CONSERVATIVE_SIZE",
            "sized_quantity",
        ),
        ({"daily_loss": 500.0}, "DAILY_LOSS_LIMIT_BREACHED", "daily_loss"),
        ({"account_loss": 1_000.0}, "ACCOUNT_LOSS_LIMIT_BREACHED", "account_loss"),
        ({"strategy_loss": 250.0}, "STRATEGY_LOSS_LIMIT_BREACHED", "strategy_loss"),
        ({"duplicate_intent": True}, "DUPLICATE_INTENT", "duplicate_intent"),
        ({"conflicting_intent": True}, "CONFLICTING_INTENT", "conflicting_intent"),
    ],
)
def test_risk_table_rejects_entries_with_stable_evidence(
    updates: dict[str, object], reason_code: str, observed_key: str
) -> None:
    decision = evaluate_entry_risk(_context(**updates))

    assert decision.approved is False
    assert decision.reason_code == reason_code
    assert observed_key in decision.observed_values
    assert decision.idempotency_key == "intent-1"


def test_clean_entry_is_approved_and_decision_identity_is_stable() -> None:
    first = evaluate_entry_risk(_context())
    repeated = evaluate_entry_risk(_context())

    assert first.approved is True
    assert first.reason_code == "ENTRY_RISK_APPROVED"
    assert first == repeated
    assert first.observed_values["requested_quantity"] == 10
    assert first.observed_values["required_cash"] == 1_000.0


def test_first_failing_gate_is_deterministic() -> None:
    decision = evaluate_entry_risk(
        _context(
            intent=_intent(symbol="AAPL"),
            storage_circuit_open=True,
            duplicate_intent=True,
        )
    )

    assert decision.reason_code == "SYMBOL_NOT_ALLOWED"
