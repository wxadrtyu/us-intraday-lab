from __future__ import annotations

import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from us_intraday_lab.contracts.market import MarketBarClosed
from us_intraday_lab.contracts.orders import OrderIntent
from us_intraday_lab.contracts.paper import (
    BrokerOrder,
    BrokerPosition,
    PaperCheckpoint,
    PaperSession,
    PositionSnapshot,
    RiskDecision,
)
from us_intraday_lab.paper.recovery import (
    RecoveryIntegrityError,
    build_order_idempotency_key,
    recover_session,
    replay_evidence,
)
from us_intraday_lab.paper.store import PaperStore

NOW = datetime(2026, 8, 3, 14, 0, tzinfo=UTC)
SESSION_ID = "paper-session-2026-08-03"


def _session() -> PaperSession:
    return PaperSession(
        paper_session_id=SESSION_ID,
        session_date=date(2026, 8, 3),
        broker_account_id="fake-paper-account",
        broker_sdk_version="fake-1.0",
        created_at=NOW,
    )


def _bar(slot: int) -> MarketBarClosed:
    start = NOW + timedelta(minutes=slot)
    return MarketBarClosed(
        provider_event_id=f"alpaca:iex:SPY:{start.isoformat()}",
        symbol="SPY",
        timeframe="1min",
        bar_start=start,
        bar_end=start + timedelta(minutes=1),
        available_at=start + timedelta(minutes=1),
        open=100.0 + slot,
        high=101.0 + slot,
        low=99.0 + slot,
        close=100.5 + slot,
        volume=1_000,
    )


def _position_snapshot(slot: int, *, quantity: int) -> PositionSnapshot:
    positions = (
        (
            BrokerPosition(
                asset_id="asset-spy",
                symbol="SPY",
                quantity=quantity,
                average_entry_price=100.0,
                market_value=quantity * 100.0,
                observed_at=NOW + timedelta(minutes=slot),
            ),
        )
        if quantity
        else ()
    )
    return PositionSnapshot(
        snapshot_id=f"snapshot-{slot}",
        paper_session_id=SESSION_ID,
        positions=positions,
        observed_at=NOW + timedelta(minutes=slot),
    )


def _intent() -> OrderIntent:
    return OrderIntent(
        schema_version="1.0.0",
        run_id=SESSION_ID,
        strategy_id="strategy-1",
        symbol="SPY",
        session=date(2026, 8, 3),
        side="buy",
        order_type="market",
        quantity=10,
        signal_time=NOW + timedelta(minutes=1),
        eligible_time=NOW + timedelta(minutes=2),
        reason_code="entry_signal",
        idempotency_key="intent-1",
    )


def _risk() -> RiskDecision:
    return RiskDecision(
        decision_id="risk-1",
        idempotency_key="intent-1",
        approved=True,
        reason_code="RISK_APPROVED",
        observed_values={"cash": 25_000.0},
        decided_at=NOW + timedelta(minutes=2),
    )


def _order() -> BrokerOrder:
    return BrokerOrder(
        broker_order_id="broker-order-1",
        client_order_id="intent-1",
        symbol="SPY",
        side="buy",
        order_type="market",
        status="accepted",
        quantity=10,
        filled_quantity=0,
        average_fill_price=None,
        submitted_at=NOW + timedelta(minutes=2),
        updated_at=NOW + timedelta(minutes=2),
        rejection_reason=None,
    )


def _seed_with_verified_checkpoint(store: PaperStore) -> PaperCheckpoint:
    store.create_session(_session())
    first_bar = _bar(0)
    empty_snapshot = _position_snapshot(1, quantity=0)
    store.append_market_event(SESSION_ID, first_bar)
    store.append_position_snapshot(empty_snapshot)
    prefix = replay_evidence(
        paper_session_id=SESSION_ID,
        market_events=(first_bar,),
        order_events=(_order(),),
        position_snapshots=(empty_snapshot,),
    )
    checkpoint = PaperCheckpoint(
        checkpoint_id="checkpoint-1",
        paper_session_id=SESSION_ID,
        event_sequence=1,
        state_sha256=prefix.content_sha256,
        created_at=NOW + timedelta(minutes=2),
    )
    store.record_order_bundle(
        intent=_intent(),
        risk_decision=_risk(),
        broker_order=_order(),
        checkpoint=checkpoint,
    )
    return checkpoint


def test_resume_after_verified_checkpoint_matches_clean_full_replay(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "paper.sqlite3")
    checkpoint = _seed_with_verified_checkpoint(store)
    later_bar = _bar(2)
    later_snapshot = _position_snapshot(3, quantity=10)
    store.append_market_event(SESSION_ID, later_bar)
    store.append_position_snapshot(later_snapshot)

    recovered = recover_session(store=store, paper_session_id=SESSION_ID)
    clean = replay_evidence(
        paper_session_id=SESSION_ID,
        market_events=store.list_market_events(SESSION_ID),
        order_events=store.list_order_events(SESSION_ID),
        position_snapshots=store.list_position_snapshots(SESSION_ID),
    )
    assert recovered.resumed_from_checkpoint_id == checkpoint.checkpoint_id
    assert recovered.state == clean
    assert recovered.state.content_sha256 == recovered.clean_replay_sha256
    assert recovered.replayed_after_checkpoint == 2


def test_bad_checkpoint_hash_fails_closed(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "paper.sqlite3")
    store.create_session(_session())
    checkpoint = PaperCheckpoint(
        checkpoint_id="checkpoint-1",
        paper_session_id=SESSION_ID,
        event_sequence=1,
        state_sha256="f" * 64,
        created_at=NOW + timedelta(minutes=2),
    )
    store.record_order_bundle(
        intent=_intent(),
        risk_decision=_risk(),
        broker_order=_order(),
        checkpoint=checkpoint,
    )
    with pytest.raises(RecoveryIntegrityError, match="CHECKPOINT_STATE_HASH_MISMATCH"):
        recover_session(store=store, paper_session_id=SESSION_ID)


def test_duplicate_market_event_after_restart_is_not_replayed_twice(tmp_path: Path) -> None:
    path = tmp_path / "paper.sqlite3"
    first = PaperStore(path)
    first.create_session(_session())
    first.append_market_event(SESSION_ID, _bar(0))
    restarted = PaperStore(path)
    restarted.append_market_event(SESSION_ID, _bar(0))
    state = recover_session(store=restarted, paper_session_id=SESSION_ID).state
    assert state.processed_provider_event_ids == (_bar(0).provider_event_id,)


def test_task2_database_is_upgraded_with_replay_generation_columns(tmp_path: Path) -> None:
    path = tmp_path / "paper.sqlite3"
    initial = (
        Path(__file__).resolve().parents[3]
        / "src"
        / "us_intraday_lab"
        / "paper"
        / "migrations"
        / "001_initial.sql"
    )
    with sqlite3.connect(path, isolation_level=None) as connection:
        connection.executescript(initial.read_text(encoding="utf-8"))

    PaperStore(path)
    with sqlite3.connect(path) as connection:
        assert "checkpoint_base_sequence" in {
            str(row[1]) for row in connection.execute("PRAGMA table_info(market_events)")
        }
        assert "checkpoint_sequence" in {
            str(row[1]) for row in connection.execute("PRAGMA table_info(order_events)")
        }


def test_order_idempotency_key_is_stable_bounded_and_input_sensitive() -> None:
    arguments = {
        "paper_session_id": SESSION_ID,
        "strategy_id": "strategy-1",
        "symbol": "SPY",
        "signal_available_at": NOW,
        "action": "entry",
        "entry_sequence": 1,
    }
    first = build_order_idempotency_key(**arguments)  # type: ignore[arg-type]
    assert first == build_order_idempotency_key(**arguments)  # type: ignore[arg-type]
    assert len(first) <= 48
    changed = {
        build_order_idempotency_key(
            **{**arguments, field: value}  # type: ignore[arg-type]
        )
        for field, value in (
            ("paper_session_id", "other-session"),
            ("strategy_id", "strategy-2"),
            ("symbol", "QQQ"),
            ("signal_available_at", NOW + timedelta(minutes=1)),
            ("action", "exit"),
            ("entry_sequence", 2),
        )
    }
    assert len(changed) == 6
    assert first not in changed


def test_idempotency_key_rejects_naive_time_and_unapproved_inputs() -> None:
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        build_order_idempotency_key(
            paper_session_id=SESSION_ID,
            strategy_id="strategy-1",
            symbol="SPY",
            signal_available_at=NOW.replace(tzinfo=None),
            action="entry",
            entry_sequence=1,
        )
    with pytest.raises(ValueError, match="production symbol"):
        build_order_idempotency_key(
            paper_session_id=SESSION_ID,
            strategy_id="strategy-1",
            symbol="AAPL",
            signal_available_at=NOW,
            action="entry",
            entry_sequence=1,
        )
