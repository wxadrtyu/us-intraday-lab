from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from tests.fakes.broker import FakePaperBroker
from us_intraday_lab.contracts.paper import (
    BrokerOrder,
    BrokerPosition,
    PaperSession,
)
from us_intraday_lab.paper.reconciliation import (
    STARTUP_SEQUENCE,
    evaluate_reconciliation,
    run_startup_reconciliation,
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


def _order(
    *,
    key: str = "intent-1",
    broker_id: str = "broker-order-1",
    status: str = "accepted",
    quantity: int = 10,
    filled_quantity: int = 0,
) -> BrokerOrder:
    return BrokerOrder(
        broker_order_id=broker_id,
        client_order_id=key,
        symbol="SPY",
        side="buy",
        order_type="market",
        status=status,
        quantity=quantity,
        filled_quantity=filled_quantity,
        average_fill_price=100.0 if filled_quantity else None,
        submitted_at=NOW,
        updated_at=NOW,
        rejection_reason=None,
    )


def _position(*, quantity: int = 10, symbol: str = "SPY") -> BrokerPosition:
    return BrokerPosition(
        asset_id=f"asset-{symbol.lower()}",
        symbol=symbol,
        quantity=quantity,
        average_entry_price=100.0,
        market_value=quantity * 100.0,
        observed_at=NOW,
    )


def _evaluate(
    *,
    local_orders: tuple[BrokerOrder, ...] = (),
    local_positions: tuple[BrokerPosition, ...] = (),
    broker_orders: tuple[BrokerOrder, ...] = (),
    broker_positions: tuple[BrokerPosition, ...] = (),
):
    return evaluate_reconciliation(
        paper_session_id=SESSION_ID,
        local_orders=local_orders,
        local_positions=local_positions,
        broker_orders=broker_orders,
        broker_positions=broker_positions,
        completed_at=NOW,
    )


def test_clean_flat_and_matching_exposure_enable_entries() -> None:
    flat = _evaluate()
    assert flat.status == "clean"
    assert flat.entries_enabled
    assert flat.exits_enabled
    assert flat.discrepancy_codes == ()

    matching = _evaluate(
        local_orders=(_order(),),
        local_positions=(_position(),),
        broker_orders=(_order(),),
        broker_positions=(_position(),),
    )
    assert matching.status == "clean"
    assert matching.entries_enabled


@pytest.mark.parametrize(
    ("local_positions", "broker_positions", "reason"),
    [
        ((), (_position(),), "BROKER_POSITION_MISSING_LOCALLY"),
        ((_position(),), (), "LOCAL_POSITION_MISSING_AT_BROKER"),
        ((_position(quantity=9),), (_position(quantity=10),), "POSITION_QUANTITY_MISMATCH"),
    ],
)
def test_unexplained_exposure_mismatches_block_entries(
    local_positions: tuple[BrokerPosition, ...],
    broker_positions: tuple[BrokerPosition, ...],
    reason: str,
) -> None:
    result = _evaluate(
        local_positions=local_positions,
        broker_positions=broker_positions,
    )
    assert result.status == "blocked"
    assert not result.entries_enabled
    assert result.exits_enabled
    assert reason in result.discrepancy_codes


def test_unknown_broker_order_and_missing_local_open_order_block() -> None:
    unknown = _evaluate(broker_orders=(_order(key="unknown"),))
    assert unknown.status == "blocked"
    assert "UNKNOWN_BROKER_ORDER" in unknown.discrepancy_codes

    missing = _evaluate(local_orders=(_order(),))
    assert missing.status == "blocked"
    assert "LOCAL_OPEN_ORDER_MISSING_AT_BROKER" in missing.discrepancy_codes


def test_locally_pending_entry_filled_at_broker_is_recoverable_but_not_yet_enabled() -> None:
    result = _evaluate(
        local_orders=(_order(),),
        broker_positions=(_position(),),
    )
    assert result.status == "recoverable"
    assert not result.entries_enabled
    assert result.exits_enabled
    assert result.discrepancy_codes == ("PENDING_ENTRY_FILLED_AT_BROKER",)


def test_startup_sequence_reads_broker_truth_and_persists_result(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "paper.sqlite3")
    store.create_session(_session())
    broker = FakePaperBroker(now=NOW)

    result = run_startup_reconciliation(
        store=store,
        broker=broker,
        paper_session_id=SESSION_ID,
        completed_at=NOW,
    )

    assert result.status == "clean"
    assert result.startup_steps == STARTUP_SEQUENCE
    assert result.broker_account_id == broker.account().account_id
    assert store.list_reconciliation_runs(SESSION_ID) == (result,)


def test_reconciliation_result_is_exactly_idempotent(tmp_path: Path) -> None:
    store = PaperStore(tmp_path / "paper.sqlite3")
    store.create_session(_session())
    broker = FakePaperBroker(now=NOW)
    first = run_startup_reconciliation(
        store=store,
        broker=broker,
        paper_session_id=SESSION_ID,
        completed_at=NOW,
    )
    repeated = run_startup_reconciliation(
        store=store,
        broker=broker,
        paper_session_id=SESSION_ID,
        completed_at=NOW,
    )
    assert repeated == first
    assert len(store.list_reconciliation_runs(SESSION_ID)) == 1


def test_startup_blocks_when_session_is_bound_to_another_broker_account(
    tmp_path: Path,
) -> None:
    store = PaperStore(tmp_path / "paper.sqlite3")
    store.create_session(_session().model_copy(update={"broker_account_id": "other-account"}))
    result = run_startup_reconciliation(
        store=store,
        broker=FakePaperBroker(now=NOW),
        paper_session_id=SESSION_ID,
        completed_at=NOW,
    )
    assert result.status == "blocked"
    assert not result.entries_enabled
    assert result.discrepancy_codes == ("BROKER_ACCOUNT_MISMATCH",)
