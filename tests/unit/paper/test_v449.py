from datetime import UTC, date, datetime

import pytest

from tests.fakes.broker import FakePaperBroker, SubmitBehavior
from us_intraday_lab.paper.v449 import SleeveSignal, V449PaperController, V449PaperLedger

SESSION = date(2026, 8, 24)
NOW = datetime(2026, 8, 24, 15, 30, tzinfo=UTC)


def _signal(sleeve: str, weight: float) -> SleeveSignal:
    return SleeveSignal(
        sleeve=sleeve,  # type: ignore[arg-type]
        symbol="TQQQ",
        decision_bar=23,
        exit_bar=65 if sleeve == "component" else 72,
        weight=weight,
        exposure=1.0,
    )


def test_two_sleeves_are_sized_cash_only_and_exit_independently(tmp_path) -> None:
    broker = FakePaperBroker(now=NOW)
    broker.queue_submit_behavior(SubmitBehavior.FILL)
    broker.queue_submit_behavior(SubmitBehavior.FILL)
    controller = V449PaperController(
        broker=broker, ledger=V449PaperLedger(tmp_path / "v449.sqlite3")
    )

    component = controller.enter(
        session_date=SESSION, signal=_signal("component", 0.05), reference_price=100.0, now=NOW
    )
    anchor = controller.enter(
        session_date=SESSION, signal=_signal("anchor", 0.95), reference_price=100.0, now=NOW
    )

    assert component is not None and component.quantity == 12
    assert anchor is not None and anchor.quantity == 235
    assert sum(item.quantity for item in broker.positions()) == 247

    broker.queue_submit_behavior(SubmitBehavior.FILL)
    controller.exit_sleeve(session_date=SESSION, sleeve="component", now=NOW)
    assert broker.positions()[0].quantity == 235
    broker.queue_submit_behavior(SubmitBehavior.FILL)
    controller.exit_sleeve(session_date=SESSION, sleeve="anchor", now=NOW)
    assert broker.positions() == ()


def test_restart_recovers_order_by_client_id_without_resubmission(tmp_path) -> None:
    broker = FakePaperBroker(now=NOW)
    broker.queue_submit_behavior(SubmitBehavior.FILL)
    ledger = V449PaperLedger(tmp_path / "v449.sqlite3")
    first = V449PaperController(broker=broker, ledger=ledger)
    first.enter(
        session_date=SESSION, signal=_signal("component", 0.05), reference_price=100.0, now=NOW
    )
    second = V449PaperController(broker=broker, ledger=ledger)

    second.startup_check(SESSION)

    assert (
        second.enter(
            session_date=SESSION,
            signal=_signal("component", 0.05),
            reference_price=100.0,
            now=NOW,
        )
        is None
    )
    assert len(broker.submitted_idempotency_keys) == 1


def test_startup_blocks_contaminated_account(tmp_path) -> None:
    broker = FakePaperBroker(now=NOW)
    broker.force_position(symbol="SPY", quantity=1, price=100.0)
    controller = V449PaperController(
        broker=broker, ledger=V449PaperLedger(tmp_path / "v449.sqlite3")
    )

    with pytest.raises(RuntimeError, match="DEDICATED_ACCOUNT_CONTAMINATED"):
        controller.startup_check(SESSION)


def test_partial_entry_is_cancelled_then_only_filled_quantity_is_exited(tmp_path) -> None:
    broker = FakePaperBroker(now=NOW)
    broker.queue_submit_behavior(SubmitBehavior.PARTIAL_FILL)
    controller = V449PaperController(
        broker=broker, ledger=V449PaperLedger(tmp_path / "v449.sqlite3")
    )
    entry = controller.enter(
        session_date=SESSION, signal=_signal("component", 0.05), reference_price=100.0, now=NOW
    )
    assert entry is not None and entry.filled_quantity == 6

    broker.queue_submit_behavior(SubmitBehavior.FILL)
    exit_order = controller.exit_sleeve(
        session_date=SESSION, sleeve="component", now=NOW
    )

    assert exit_order is not None and exit_order.quantity == 6
    assert broker.positions() == ()


def test_emergency_flatten_is_idempotent(tmp_path) -> None:
    broker = FakePaperBroker(now=NOW)
    broker.force_position(symbol="SOXL", quantity=7, price=100.0)
    broker.queue_submit_behavior(SubmitBehavior.FILL)
    controller = V449PaperController(
        broker=broker, ledger=V449PaperLedger(tmp_path / "v449.sqlite3")
    )

    orders = controller.emergency_flatten(session_date=SESSION, now=NOW)
    assert len(orders) == 1
    assert broker.positions() == ()
    assert controller.emergency_flatten(session_date=SESSION, now=NOW) == ()


def test_ledger_rejects_updates_and_deletes(tmp_path) -> None:
    ledger = V449PaperLedger(tmp_path / "v449.sqlite3")
    assert ledger.append(
        event_key="one", session_date=SESSION, event_type="TEST", payload={"value": 1}
    )
    with pytest.raises(Exception, match="EVENTS_APPEND_ONLY"):
        ledger._connection.execute("UPDATE events SET event_type='X'")
    with pytest.raises(Exception, match="EVENTS_APPEND_ONLY"):
        ledger._connection.execute("DELETE FROM events")


def test_two_strategy_pool_respects_account_level_gross_and_reconciles(tmp_path) -> None:
    broker = FakePaperBroker(now=NOW)
    ledger = V449PaperLedger(tmp_path / "pool.sqlite3")
    v247 = V449PaperController(
        broker=broker,
        ledger=ledger,
        candidate_id="lev-v247-df683b8a37c927f6",
        strategy_code="v247",
        account_fraction=0.5,
        managed_strategy_codes=("v247", "v449"),
    )
    v449 = V449PaperController(
        broker=broker,
        ledger=ledger,
        strategy_code="v449",
        account_fraction=0.5,
        managed_strategy_codes=("v247", "v449"),
    )
    for _ in range(4):
        broker.queue_submit_behavior(SubmitBehavior.FILL)

    v247.enter(
        session_date=SESSION, signal=_signal("component", 0.05), reference_price=100.0, now=NOW
    )
    v449.enter(
        session_date=SESSION, signal=_signal("component", 0.05), reference_price=100.0, now=NOW
    )
    v247.enter(
        session_date=SESSION, signal=_signal("anchor", 0.95), reference_price=100.0, now=NOW
    )
    v449.enter(
        session_date=SESSION, signal=_signal("anchor", 0.95), reference_price=100.0, now=NOW
    )

    assert sum(position.quantity * 100.0 for position in broker.positions()) <= 25_000 * 0.99
    v449.startup_check(SESSION)


def test_pool_allocation_rejects_invalid_fraction(tmp_path) -> None:
    broker = FakePaperBroker(now=NOW)
    with pytest.raises(ValueError, match="PAPER_ACCOUNT_FRACTION_OUT_OF_RANGE"):
        V449PaperController(
            broker=broker,
            ledger=V449PaperLedger(tmp_path / "pool.sqlite3"),
            account_fraction=1.01,
        )
