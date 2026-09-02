from datetime import UTC, date, datetime

import pandas as pd
import pytest

from tests.fakes.broker import FakePaperBroker, SubmitBehavior
from us_intraday_lab.paper.pool import (
    LEGACY_FOUR_MEMBER_ALLOCATIONS,
    PAPER_ADMISSION_STATES,
    POOL_ALLOCATIONS,
    USER_REQUESTED_FOUR_WAY_ALLOCATIONS,
    V247_ID,
    V449_ID,
    V798_ID,
    V798_STATE_THRESHOLD,
    V1254_ID,
    V1254_STATE_THRESHOLD,
    V9022_ID,
    V9083_ID,
    V9100_ID,
    V10824_ID,
    V11098_ID,
    v798_state_score,
    v1254_state_score,
    validate_pool_allocations,
)
from us_intraday_lab.paper.v449 import SleeveSignal, V449PaperController, V449PaperLedger
from us_intraday_lab.v45_research_shadow import SYMBOLS

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


def _state_bars(*, omit_last_xly_minute: bool = False) -> pd.DataFrame:
    rows = []
    prior = pd.Timestamp("2026-08-21 13:30:00", tz="UTC")
    for symbol in SYMBOLS:
        for minute in range(390):
            if omit_last_xly_minute and symbol == "XLY" and minute == 389:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": prior + pd.Timedelta(minutes=minute),
                    "open": 100.0,
                    "high": 100.02,
                    "low": 99.99,
                    "close": 100.01,
                    "volume": 1000.0,
                }
            )
    rows.append(
        {
            "symbol": "SPY",
            "timestamp": pd.Timestamp("2026-08-24 13:30:00", tz="UTC"),
            "open": 100.0,
            "high": 100.0,
            "low": 100.0,
            "close": 100.0,
            "volume": 1000.0,
        }
    )
    return pd.DataFrame(rows)


def test_v798_prior_close_state_is_causal_and_matches_sparse_sector_semantics() -> None:
    score = v798_state_score(_state_bars(), session_date=SESSION)
    assert score > V798_STATE_THRESHOLD
    sparse_score = v798_state_score(
        _state_bars(omit_last_xly_minute=True), session_date=SESSION
    )
    assert sparse_score < score


def test_v1254_prior_close_state_is_finite_and_uses_sector_dispersion() -> None:
    score = v1254_state_score(_state_bars(), session_date=SESSION)
    sparse_score = v1254_state_score(
        _state_bars(omit_last_xly_minute=True), session_date=SESSION
    )
    assert score > V1254_STATE_THRESHOLD
    assert sparse_score != score


def test_consolidated_pool_allocations_are_exact() -> None:
    validate_pool_allocations()
    assert POOL_ALLOCATIONS == {V1254_ID: 1.0}
    assert sum(POOL_ALLOCATIONS.values()) == pytest.approx(1.0)


def test_noncausal_family_leaders_and_merge_fail_closed() -> None:
    assert PAPER_ADMISSION_STATES[V9022_ID] == "REJECTED_NONCAUSAL_TIMING_PARITY"
    assert PAPER_ADMISSION_STATES[V9083_ID] == "REJECTED_NONCAUSAL_TIMING_PARITY"
    assert PAPER_ADMISSION_STATES[V9100_ID] == "REJECTED_NONCAUSAL_TIMING_PARITY"
    assert V9022_ID not in POOL_ALLOCATIONS
    assert V9083_ID not in POOL_ALLOCATIONS
    assert V9100_ID not in POOL_ALLOCATIONS
    assert USER_REQUESTED_FOUR_WAY_ALLOCATIONS == {
        V1254_ID: 0.25,
        V9022_ID: 0.25,
        V9083_ID: 0.25,
        V9100_ID: 0.25,
    }
    assert sum(USER_REQUESTED_FOUR_WAY_ALLOCATIONS.values()) == pytest.approx(1.0)


def test_v10824_waits_for_execution_parity_before_paper_allocation() -> None:
    assert (
        PAPER_ADMISSION_STATES[V10824_ID]
        == "REJECTED_NONCAUSAL_EARLY_FILL_BEFORE_ROUTE_RESOLUTION"
    )
    assert V10824_ID not in POOL_ALLOCATIONS
    assert (
        PAPER_ADMISSION_STATES[V11098_ID]
        == "FORWARD_ROUTE_PARITY_PASSED_LIVE_FRAME_ADAPTER_PENDING"
    )
    assert V11098_ID not in POOL_ALLOCATIONS


def test_four_member_pool_worst_case_gross_stays_below_buffer(tmp_path) -> None:
    broker = FakePaperBroker(now=NOW)
    ledger = V449PaperLedger(tmp_path / "four-member-pool.sqlite3")
    definitions = (
        ("v247", V247_ID, 0.95, 0.05),
        ("v449", V449_ID, 0.95, 0.05),
        ("v798", V798_ID, 0.90, 0.10),
        ("v1254", V1254_ID, 0.84, 0.16),
    )
    controllers = []
    for strategy_code, candidate_id, _, _ in definitions:
        controllers.append(
            V449PaperController(
                broker=broker,
                ledger=ledger,
                candidate_id=candidate_id,
                strategy_code=strategy_code,
                account_fraction=LEGACY_FOUR_MEMBER_ALLOCATIONS[candidate_id],
                managed_strategy_codes=("v247", "v449", "v798", "v1254"),
            )
        )
    for _ in range(8):
        broker.queue_submit_behavior(SubmitBehavior.FILL)
    for controller, (_, _, anchor_weight, component_weight) in zip(
        controllers, definitions, strict=True
    ):
        controller.enter(
            session_date=SESSION,
            signal=_signal("component", component_weight),
            reference_price=100.0,
            now=NOW,
        )
        controller.enter(
            session_date=SESSION,
            signal=_signal("anchor", anchor_weight),
            reference_price=100.0,
            now=NOW,
        )
    notional = sum(position.quantity * 100.0 for position in broker.positions())
    assert notional <= 25_000 * 0.99
    controllers[0].startup_check(SESSION)
