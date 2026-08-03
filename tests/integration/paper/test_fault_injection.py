from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from tests.fakes.broker import FakePaperBroker, SubmitBehavior
from tests.fakes.market_data import iex_minute_bar
from us_intraday_lab.contracts.market import MarketBarClosed
from us_intraday_lab.contracts.paper import PaperSession
from us_intraday_lab.paper.market_data import MarketDataPipeline
from us_intraday_lab.paper.session import PaperSessionService, SessionStrategy
from us_intraday_lab.paper.store import PaperStore
from us_intraday_lab.strategy.features import FEATURE_SET_VERSION

SESSION_DATE = date(2026, 8, 3)
SESSION_OPEN = datetime(2026, 8, 3, 13, 30, tzinfo=UTC)
EXECUTION_AT = SESSION_OPEN + timedelta(minutes=16)
SESSION_ID = "paper-session-2026-08-03"


class _Strategy:
    strategy_id = "strategy-spy"
    symbol = "SPY"
    lifecycle_state = "paper_shadow"
    stop_loss_bps = 50
    risk_fraction = 0.005
    max_position_fraction = 0.25
    daily_loss_limit = 500.0
    account_loss_limit = 1_000.0
    strategy_loss_limit = 250.0

    def should_enter(self, bar: MarketBarClosed) -> bool:
        return bar.symbol == "SPY"


def _bars() -> tuple[MarketBarClosed, ...]:
    return tuple(
        iex_minute_bar(symbol="SPY", bar_start=SESSION_OPEN + timedelta(minutes=index))
        for index in range(15)
    )


def _components(tmp_path: Path) -> tuple[PaperStore, FakePaperBroker, PaperSessionService]:
    store = PaperStore(tmp_path / "paper.sqlite3")
    store.create_session(
        PaperSession(
            paper_session_id=SESSION_ID,
            session_date=SESSION_DATE,
            broker_account_id="fake-paper-account",
            broker_sdk_version="fake-1.0",
            status="running",
            created_at=SESSION_OPEN,
        )
    )
    broker = FakePaperBroker(now=EXECUTION_AT)
    pipeline = MarketDataPipeline(
        store=store,
        paper_session_id=SESSION_ID,
        session_date=SESSION_DATE,
        reorder_window=timedelta(minutes=2),
        stale_after=timedelta(minutes=2),
        expected_market_schema_version="1.0.0",
        expected_feature_set_version=FEATURE_SET_VERSION,
        required_symbols=("SPY",),
    )
    strategy: SessionStrategy = _Strategy()
    service = PaperSessionService(
        store=store,
        broker=broker,
        market_data=pipeline,
        strategies=(strategy,),
        session_date=SESSION_DATE,
        closeout_buffer_minutes=5,
    )
    service.start(completed_at=SESSION_OPEN)
    return store, broker, service


def _restart(*, store: PaperStore, broker: FakePaperBroker) -> PaperSessionService:
    pipeline = MarketDataPipeline(
        store=store,
        paper_session_id=SESSION_ID,
        session_date=SESSION_DATE,
        reorder_window=timedelta(minutes=2),
        stale_after=timedelta(minutes=2),
        expected_market_schema_version="1.0.0",
        expected_feature_set_version=FEATURE_SET_VERSION,
        required_symbols=("SPY",),
    )
    strategy: SessionStrategy = _Strategy()
    return PaperSessionService(
        store=store,
        broker=broker,
        market_data=pipeline,
        strategies=(strategy,),
        session_date=SESSION_DATE,
        closeout_buffer_minutes=5,
    )


def test_disconnect_stale_feed_and_open_store_circuit_disable_entries(tmp_path: Path) -> None:
    _store, broker, service = _components(tmp_path)
    broker.disconnect()
    disconnected = service.process_bars(_bars(), observed_at=EXECUTION_AT)
    assert disconnected.entries_enabled is False
    assert disconnected.submitted_entry_count == 0
    assert broker.submitted_idempotency_keys == []

    _stale_store, stale_broker, stale_service = _components(tmp_path / "stale")
    stale = stale_service.process_bars(_bars(), observed_at=EXECUTION_AT + timedelta(minutes=3))
    assert stale.entries_enabled is False
    assert "MARKET_DATA_STALE" in stale.reason_codes
    assert stale_broker.submitted_idempotency_keys == []

    circuit_store, circuit_broker, circuit_service = _components(tmp_path / "circuit")
    circuit_store._entry_writes_disabled = True
    circuit = circuit_service.process_bars(_bars(), observed_at=EXECUTION_AT)
    assert circuit.entries_enabled is False
    assert circuit.reason_codes == ("STORAGE_CIRCUIT_OPEN",)
    assert circuit_broker.submitted_idempotency_keys == []


def test_timeout_after_broker_acceptance_blocks_restart_without_duplicate_submission(
    tmp_path: Path,
) -> None:
    store, broker, service = _components(tmp_path)
    broker.queue_submit_behavior(SubmitBehavior.TIMEOUT_AFTER_ACCEPT)

    uncertain = service.process_bars(_bars(), observed_at=EXECUTION_AT)
    assert uncertain.entries_enabled is False
    assert uncertain.reason_codes == ("BROKER_SUBMISSION_UNCERTAIN",)
    assert len(broker.submitted_idempotency_keys) == 1

    restarted = _restart(store=store, broker=broker)
    reconciliation = restarted.start(completed_at=EXECUTION_AT)
    assert reconciliation.status == "blocked"
    assert "UNKNOWN_BROKER_ORDER" in reconciliation.discrepancy_codes
    assert len(broker.submitted_idempotency_keys) == 1


def test_partial_fill_and_pending_order_restart_do_not_duplicate_entries(
    tmp_path: Path,
) -> None:
    _partial_store, partial_broker, partial_service = _components(tmp_path / "partial")
    partial_broker.queue_submit_behavior(SubmitBehavior.PARTIAL_FILL)
    partial = partial_service.process_bars(_bars(), observed_at=EXECUTION_AT)
    assert partial.submitted_entry_count == 1
    assert 0 < partial_broker.positions()[0].quantity
    partial_service.process_bars(_bars(), observed_at=EXECUTION_AT)
    assert len(partial_broker.submitted_idempotency_keys) == 1

    pending_store, pending_broker, pending_service = _components(tmp_path / "pending")
    pending = pending_service.process_bars(_bars(), observed_at=EXECUTION_AT)
    assert pending.submitted_entry_count == 1
    restarted = _restart(store=pending_store, broker=pending_broker)
    assert restarted.start(completed_at=EXECUTION_AT).status == "clean"
    repeated = restarted.process_bars(_bars(), observed_at=EXECUTION_AT)
    assert repeated.submitted_entry_count == 0
    assert len(pending_broker.submitted_idempotency_keys) == 1


def test_broker_position_mismatch_blocks_restart_and_new_entries(tmp_path: Path) -> None:
    store, broker, service = _components(tmp_path)
    broker.queue_submit_behavior(SubmitBehavior.FILL)
    assert service.process_bars(_bars(), observed_at=EXECUTION_AT).submitted_entry_count == 1
    local_quantity = broker.positions()[0].quantity
    broker.force_position(symbol="SPY", quantity=local_quantity + 1, price=100.0)

    restarted = _restart(store=store, broker=broker)
    result = restarted.start(completed_at=EXECUTION_AT)

    assert result.status == "blocked"
    assert "POSITION_QUANTITY_MISMATCH" in result.discrepancy_codes
    assert len(broker.submitted_idempotency_keys) == 1


def test_database_failure_after_broker_acceptance_opens_circuit_without_retry(
    tmp_path: Path,
) -> None:
    store, broker, service = _components(tmp_path)
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_session_checkpoint
            BEFORE INSERT ON paper_checkpoints
            BEGIN SELECT RAISE(ABORT, 'INJECTED_SESSION_CHECKPOINT_FAILURE'); END
            """
        )

    failed = service.process_bars(_bars(), observed_at=EXECUTION_AT)

    assert failed.entries_enabled is False
    assert failed.reason_codes == ("PAPER_ENTRY_FAILURE",)
    assert store.entry_writes_disabled is True
    assert len(broker.submitted_idempotency_keys) == 1
    repeated = service.process_bars(_bars(), observed_at=EXECUTION_AT)
    assert repeated.reason_codes == ("STORAGE_CIRCUIT_OPEN",)
    assert len(broker.submitted_idempotency_keys) == 1


def test_duplicate_order_update_is_persisted_once_without_resubmission(tmp_path: Path) -> None:
    store, broker, service = _components(tmp_path)
    broker.queue_submit_behavior(SubmitBehavior.DELAYED_FILL)
    assert service.process_bars(_bars(), observed_at=EXECUTION_AT).submitted_entry_count == 1
    key = broker.submitted_idempotency_keys[0]
    filled = broker.fill_delayed(key)

    assert service.process_order_update(filled, observed_at=EXECUTION_AT) is True
    assert service.process_order_update(filled, observed_at=EXECUTION_AT) is False
    statuses = tuple(item.status for item in store.list_order_events(SESSION_ID))
    assert statuses == ("submitted", "filled")
    assert len(broker.submitted_idempotency_keys) == 1
