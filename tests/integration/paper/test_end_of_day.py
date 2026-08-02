from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from tests.fakes.broker import FakePaperBroker, SubmitBehavior
from us_intraday_lab.contracts.orders import OrderIntent
from us_intraday_lab.contracts.paper import PaperSession
from us_intraday_lab.paper.closeout import closeout_session
from us_intraday_lab.paper.store import PaperStore

NOW = datetime(2026, 8, 3, 19, 55, tzinfo=UTC)
SESSION_ID = "paper-session-2026-08-03"


def _store(tmp_path: Path) -> PaperStore:
    store = PaperStore(tmp_path / "paper.sqlite3")
    store.create_session(
        PaperSession(
            paper_session_id=SESSION_ID,
            session_date=date(2026, 8, 3),
            broker_account_id="fake-paper-account",
            broker_sdk_version="fake-1.0",
            status="running",
            created_at=NOW - timedelta(hours=6),
        )
    )
    return store


def _opening_intent() -> OrderIntent:
    return OrderIntent(
        schema_version="1.0.0",
        run_id=SESSION_ID,
        strategy_id="strategy-spy",
        symbol="SPY",
        session=date(2026, 8, 3),
        side="buy",
        order_type="market",
        quantity=5,
        signal_time=NOW - timedelta(minutes=2),
        eligible_time=NOW - timedelta(minutes=1),
        reason_code="entry_signal",
        idempotency_key="opening-intent",
    )


def test_closeout_cancels_opening_orders_exits_longs_and_persists_flat_snapshot(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    broker = FakePaperBroker(now=NOW)
    opening = broker.submit(_opening_intent())
    broker.force_position(symbol="SPY", quantity=5, price=100.0)
    broker.queue_submit_behavior(SubmitBehavior.FILL)

    result = closeout_session(
        broker=broker,
        store=store,
        paper_session_id=SESSION_ID,
        strategy_ids_by_symbol={"SPY": "strategy-spy"},
        closeout_at=NOW,
        max_cancel_polls=3,
        max_exit_attempts=3,
        max_flat_polls=3,
    )

    assert result.entries_enabled is False
    assert result.clean is True
    assert result.status == "closed"
    assert result.cancelled_broker_order_ids == (opening.broker_order_id,)
    assert broker.open_orders() == ()
    assert broker.positions() == ()
    assert store.list_position_snapshots(SESSION_ID)[-1].positions == ()
    assert store.list_incidents(SESSION_ID) == ()


def test_rejected_exit_retries_same_key_and_records_overnight_incident(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    broker = FakePaperBroker(now=NOW)
    broker.force_position(symbol="QQQ", quantity=7, price=200.0)
    broker.queue_submit_behavior(SubmitBehavior.REJECT)

    result = closeout_session(
        broker=broker,
        store=store,
        paper_session_id=SESSION_ID,
        strategy_ids_by_symbol={"QQQ": "strategy-qqq"},
        closeout_at=NOW,
        max_cancel_polls=2,
        max_exit_attempts=3,
        max_flat_polls=2,
    )

    attempts = broker.submit_attempted_idempotency_keys
    assert len(attempts) == 3
    assert len(set(attempts)) == 1
    assert result.entries_enabled is False
    assert result.clean is False
    assert result.status == "blocked"
    assert tuple(item.symbol for item in result.remaining_positions) == ("QQQ",)
    incidents = store.list_incidents(SESSION_ID)
    assert len(incidents) == 1
    assert incidents[0].reason_code == "OVERNIGHT_RISK_INCIDENT"
    assert incidents[0].severity == "critical"
    assert incidents[0].observed_values["remaining_symbols"] == "QQQ"
    assert store.list_position_snapshots(SESSION_ID)[-1].positions == result.remaining_positions
