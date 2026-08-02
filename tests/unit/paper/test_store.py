from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from us_intraday_lab.contracts.market import MarketBarClosed
from us_intraday_lab.contracts.orders import OrderIntent
from us_intraday_lab.contracts.paper import (
    BrokerOrder,
    PaperCheckpoint,
    PaperSession,
    PositionSnapshot,
    RiskDecision,
)
from us_intraday_lab.paper.store import (
    PaperIdempotencyConflict,
    PaperImmutableConflict,
    PaperStore,
    PaperStoreCircuitOpen,
)

NOW = datetime(2026, 8, 3, 14, 0, tzinfo=UTC)


@pytest.fixture
def store(tmp_path: Path) -> PaperStore:
    return PaperStore(tmp_path / "paper.sqlite3")


def _session() -> PaperSession:
    return PaperSession(
        paper_session_id="paper-session-2026-08-03",
        session_date=date(2026, 8, 3),
        broker_account_id="fake-paper-account",
        broker_sdk_version="0.43.5",
        created_at=NOW,
    )


def _intent(*, key: str = "intent-1", quantity: int = 10) -> OrderIntent:
    return OrderIntent(
        schema_version="1.0.0",
        run_id=_session().paper_session_id,
        strategy_id="strategy-1",
        symbol="SPY",
        session=_session().session_date,
        side="buy",
        order_type="market",
        quantity=quantity,
        signal_time=NOW,
        eligible_time=NOW + timedelta(minutes=1),
        reason_code="entry_signal",
        idempotency_key=key,
    )


def _risk(*, key: str = "intent-1") -> RiskDecision:
    return RiskDecision(
        decision_id=f"risk-{key}",
        idempotency_key=key,
        approved=True,
        reason_code="RISK_APPROVED",
        observed_values={"cash": 25_000.0, "positions": 0},
        decided_at=NOW + timedelta(minutes=1),
    )


def _order(*, key: str = "intent-1", status: str = "accepted", quantity: int = 10) -> BrokerOrder:
    return BrokerOrder(
        broker_order_id=f"broker-{key}",
        client_order_id=key,
        symbol="SPY",
        side="buy",
        order_type="market",
        status=status,
        quantity=quantity,
        filled_quantity=0,
        average_fill_price=None,
        submitted_at=NOW + timedelta(minutes=1),
        updated_at=NOW + timedelta(minutes=1),
        rejection_reason=None,
    )


def _checkpoint(*, sequence: int = 1, suffix: str = "1") -> PaperCheckpoint:
    return PaperCheckpoint(
        checkpoint_id=f"checkpoint-{suffix}",
        paper_session_id=_session().paper_session_id,
        event_sequence=sequence,
        state_sha256=suffix.rjust(64, "0"),
        created_at=NOW + timedelta(minutes=sequence),
    )


def _bar(*, close: float = 100.5) -> MarketBarClosed:
    return MarketBarClosed(
        provider_event_id="alpaca:iex:SPY:2026-08-03T14:00:00Z",
        symbol="SPY",
        timeframe="1min",
        bar_start=NOW,
        bar_end=NOW + timedelta(minutes=1),
        available_at=NOW + timedelta(minutes=1),
        open=100.0,
        high=max(101.0, close),
        low=99.0,
        close=close,
        volume=1_000,
    )


def test_schema_enables_wal_foreign_keys_busy_timeout_and_exact_tables(
    store: PaperStore,
) -> None:
    pragmas = store.connection_pragmas()
    assert pragmas["journal_mode"].lower() == "wal"
    assert pragmas["foreign_keys"] == 1
    assert pragmas["busy_timeout"] >= 5_000
    assert set(store.table_names()) == {
        "incident_events",
        "market_events",
        "order_events",
        "order_intents",
        "paper_checkpoints",
        "paper_sessions",
        "position_snapshots",
        "reconciliation_runs",
        "risk_decisions",
        "strategy_session_state",
    }


def test_order_intent_risk_event_and_checkpoint_commit_atomically(store: PaperStore) -> None:
    store.create_session(_session())
    result = store.record_order_bundle(
        intent=_intent(),
        risk_decision=_risk(),
        broker_order=_order(),
        checkpoint=_checkpoint(),
    )

    assert result.intent == _intent()
    assert result.risk_decision == _risk()
    assert result.broker_order == _order()
    assert result.checkpoint == _checkpoint()
    assert store.get_session(_session().paper_session_id) == _session()
    assert store.get_order_intent(_intent().idempotency_key) == _intent()
    assert store.list_order_events(_session().paper_session_id) == (_order(),)
    assert store.latest_checkpoint(_session().paper_session_id) == _checkpoint()
    assert store.row_counts() == {
        "incident_events": 0,
        "market_events": 0,
        "order_events": 1,
        "order_intents": 1,
        "paper_checkpoints": 1,
        "paper_sessions": 1,
        "position_snapshots": 0,
        "reconciliation_runs": 0,
        "risk_decisions": 1,
        "strategy_session_state": 0,
    }


def test_exact_retry_returns_original_and_changed_intent_conflicts(store: PaperStore) -> None:
    store.create_session(_session())
    arguments = {
        "intent": _intent(),
        "risk_decision": _risk(),
        "broker_order": _order(),
        "checkpoint": _checkpoint(),
    }
    first = store.record_order_bundle(**arguments)  # type: ignore[arg-type]
    repeated = store.record_order_bundle(**arguments)  # type: ignore[arg-type]
    assert repeated == first
    assert store.row_counts()["order_events"] == 1

    with pytest.raises(PaperIdempotencyConflict, match="IDEMPOTENCY_KEY_CONTENT_MISMATCH"):
        store.record_order_bundle(
            intent=_intent(quantity=11),
            risk_decision=_risk(),
            broker_order=_order(quantity=11),
            checkpoint=_checkpoint(),
        )
    assert store.row_counts()["order_intents"] == 1


def test_new_broker_status_for_same_intent_appends_new_immutable_event(
    store: PaperStore,
) -> None:
    store.create_session(_session())
    first = store.record_order_bundle(
        intent=_intent(),
        risk_decision=_risk(),
        broker_order=_order(),
        checkpoint=_checkpoint(),
    )
    filled = _order().model_copy(
        update={
            "status": "filled",
            "filled_quantity": 10,
            "average_fill_price": 100.25,
            "updated_at": NOW + timedelta(minutes=2),
        }
    )
    second = store.record_order_bundle(
        intent=_intent(),
        risk_decision=_risk(),
        broker_order=filled,
        checkpoint=_checkpoint(sequence=2, suffix="2"),
    )
    assert first.order_event_id != second.order_event_id
    assert store.row_counts()["order_events"] == 2
    assert store.row_counts()["order_intents"] == 1
    assert store.row_counts()["risk_decisions"] == 1


def test_checkpoint_sequence_and_causal_timestamps_are_enforced(store: PaperStore) -> None:
    store.create_session(_session())
    with pytest.raises(PaperImmutableConflict, match="CHECKPOINT_SEQUENCE_GAP"):
        store.record_order_bundle(
            intent=_intent(),
            risk_decision=_risk(),
            broker_order=_order(),
            checkpoint=_checkpoint(sequence=2, suffix="2"),
        )
    assert store.row_counts()["order_intents"] == 0

    early_order = _order().model_copy(update={"submitted_at": NOW, "updated_at": NOW})
    with pytest.raises(ValueError, match="must not precede intent eligibility"):
        store.record_order_bundle(
            intent=_intent(),
            risk_decision=_risk(),
            broker_order=early_order,
            checkpoint=_checkpoint(),
        )

    late_risk = _risk().model_copy(update={"decided_at": NOW + timedelta(minutes=2)})
    with pytest.raises(ValueError, match="risk decision must not follow"):
        store.record_order_bundle(
            intent=_intent(),
            risk_decision=late_risk,
            broker_order=_order(),
            checkpoint=_checkpoint(),
        )


def test_provider_event_id_is_exactly_idempotent(store: PaperStore) -> None:
    store.create_session(_session())
    assert store.append_market_event(_session().paper_session_id, _bar()) == _bar()
    assert store.append_market_event(_session().paper_session_id, _bar()) == _bar()
    assert store.row_counts()["market_events"] == 1
    assert store.list_market_events(_session().paper_session_id) == (_bar(),)

    with pytest.raises(PaperIdempotencyConflict, match="PROVIDER_EVENT_CONTENT_MISMATCH"):
        store.append_market_event(_session().paper_session_id, _bar(close=100.75))

    other_session = _session().model_copy(update={"paper_session_id": "paper-session-other"})
    store.create_session(other_session)
    with pytest.raises(PaperIdempotencyConflict, match="PROVIDER_EVENT_CONTENT_MISMATCH"):
        store.append_market_event(other_session.paper_session_id, _bar())


def test_concurrent_same_bundle_writes_one_copy(store: PaperStore) -> None:
    store.create_session(_session())

    def write_once(_: int) -> str:
        return store.record_order_bundle(
            intent=_intent(),
            risk_decision=_risk(),
            broker_order=_order(),
            checkpoint=_checkpoint(),
        ).order_event_id

    with ThreadPoolExecutor(max_workers=4) as executor:
        event_ids = tuple(executor.map(write_once, range(8)))
    assert len(set(event_ids)) == 1
    assert store.row_counts()["order_events"] == 1


def test_wal_reader_does_not_see_uncommitted_rows(store: PaperStore) -> None:
    store.create_session(_session())
    writer = sqlite3.connect(store.path, isolation_level=None)
    try:
        writer.execute("PRAGMA foreign_keys = ON")
        writer.execute("BEGIN IMMEDIATE")
        writer.execute(
            """
            INSERT INTO incident_events (
                incident_id, paper_session_id, severity, reason_code,
                event_json, content_sha256, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "incident-uncommitted",
                _session().paper_session_id,
                "warning",
                "TEST_INCIDENT",
                "{}",
                "a" * 64,
                NOW.isoformat(),
            ),
        )
        assert store.row_counts()["incident_events"] == 0
        writer.execute("COMMIT")
        assert store.row_counts()["incident_events"] == 1
    finally:
        if writer.in_transaction:
            writer.execute("ROLLBACK")
        writer.close()


def test_injected_checkpoint_failure_rolls_back_bundle_and_opens_circuit(
    store: PaperStore,
) -> None:
    store.create_session(_session())
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_checkpoint_insert
            BEFORE INSERT ON paper_checkpoints
            BEGIN
                SELECT RAISE(ABORT, 'TEST_CHECKPOINT_FAILURE');
            END
            """
        )

    with pytest.raises(sqlite3.IntegrityError, match="TEST_CHECKPOINT_FAILURE"):
        store.record_order_bundle(
            intent=_intent(),
            risk_decision=_risk(),
            broker_order=_order(),
            checkpoint=_checkpoint(),
        )
    assert store.entry_writes_disabled
    assert store.row_counts()["order_intents"] == 0
    assert store.row_counts()["risk_decisions"] == 0
    assert store.row_counts()["order_events"] == 0
    assert store.row_counts()["paper_checkpoints"] == 0
    with pytest.raises(PaperStoreCircuitOpen, match="PAPER_STORE_WRITE_CIRCUIT_OPEN"):
        store.append_market_event(_session().paper_session_id, _bar())


def test_position_snapshots_are_immutable(store: PaperStore) -> None:
    store.create_session(_session())
    snapshot = PositionSnapshot(
        snapshot_id="snapshot-1",
        paper_session_id=_session().paper_session_id,
        positions=(),
        observed_at=NOW,
    )
    assert store.append_position_snapshot(snapshot) == snapshot
    assert store.append_position_snapshot(snapshot) == snapshot
    assert store.list_position_snapshots(_session().paper_session_id) == (snapshot,)
    changed = snapshot.model_copy(update={"observed_at": NOW + timedelta(minutes=1)})
    with pytest.raises(PaperImmutableConflict, match="IMMUTABLE_SNAPSHOT_CONFLICT"):
        store.append_position_snapshot(changed)


def test_recovery_reads_verify_retained_content_hashes(store: PaperStore) -> None:
    store.create_session(_session())
    store.record_order_bundle(
        intent=_intent(),
        risk_decision=_risk(),
        broker_order=_order(),
        checkpoint=_checkpoint(),
    )
    with sqlite3.connect(store.path) as connection:
        connection.execute("DROP TRIGGER order_intents_append_only_update")
        connection.execute(
            "UPDATE order_intents SET intent_json = '{}' WHERE idempotency_key = ?",
            (_intent().idempotency_key,),
        )

    with pytest.raises(PaperImmutableConflict, match="STORED_CONTENT_HASH_MISMATCH"):
        store.get_order_intent(_intent().idempotency_key)


@pytest.mark.parametrize(
    "table",
    [
        "market_events",
        "order_intents",
        "order_events",
        "position_snapshots",
        "risk_decisions",
        "paper_checkpoints",
        "incident_events",
    ],
)
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_raw_sql_cannot_mutate_append_only_rows(
    store: PaperStore, table: str, operation: str
) -> None:
    store.create_session(_session())
    store.append_market_event(_session().paper_session_id, _bar())
    store.record_order_bundle(
        intent=_intent(),
        risk_decision=_risk(),
        broker_order=_order(),
        checkpoint=_checkpoint(),
    )
    store.append_position_snapshot(
        PositionSnapshot(
            snapshot_id="snapshot-1",
            paper_session_id=_session().paper_session_id,
            positions=(),
            observed_at=NOW,
        )
    )
    if table == "incident_events":
        with sqlite3.connect(store.path) as connection:
            connection.execute(
                """
                INSERT INTO incident_events (
                    incident_id, paper_session_id, severity, reason_code,
                    event_json, content_sha256, occurred_at
                ) VALUES ('incident-1', ?, 'warning', 'TEST', '{}', ?, ?)
                """,
                (_session().paper_session_id, "b" * 64, NOW.isoformat()),
            )
    sql = (
        f"UPDATE {table} SET content_sha256 = content_sha256"
        if operation == "UPDATE"
        else f"DELETE FROM {table}"
    )
    with (
        sqlite3.connect(store.path) as connection,
        pytest.raises(sqlite3.IntegrityError, match="APPEND_ONLY"),
    ):
        connection.execute(sql)
