"""Compare durable local evidence with broker truth before enabling entries."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from us_intraday_lab.contracts.paper import (
    BrokerOrder,
    BrokerPosition,
    ReconciliationResult,
)
from us_intraday_lab.paper.broker import PaperBroker
from us_intraday_lab.paper.store import PaperStore

STARTUP_SEQUENCE = (
    "OPEN_STORE",
    "VERIFY_SCHEMA",
    "VERIFY_PAPER_BROKER",
    "FETCH_BROKER_CLOCK",
    "FETCH_ACCOUNT",
    "FETCH_OPEN_ORDERS",
    "FETCH_POSITIONS",
    "REPLAY_LOCAL_EVENTS",
    "COMPARE",
    "PERSIST_RECONCILIATION",
    "ENABLE_EXITS",
    "ENABLE_ENTRIES_IF_CLEAN",
)
_OPEN_STATUSES = frozenset({"submitted", "accepted", "partially_filled"})


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _evidence_hash(orders: tuple[BrokerOrder, ...], positions: tuple[BrokerPosition, ...]) -> str:
    payload = {
        "orders": [item.model_dump(mode="json") for item in orders],
        "positions": [item.model_dump(mode="json") for item in positions],
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _latest_orders(orders: tuple[BrokerOrder, ...]) -> dict[str, BrokerOrder]:
    retained: dict[str, BrokerOrder] = {}
    for order in sorted(
        orders,
        key=lambda item: (item.updated_at, item.broker_order_id, item.client_order_id),
    ):
        retained[order.client_order_id] = order
    return retained


def evaluate_reconciliation(
    *,
    paper_session_id: str,
    local_orders: tuple[BrokerOrder, ...],
    local_positions: tuple[BrokerPosition, ...],
    broker_orders: tuple[BrokerOrder, ...],
    broker_positions: tuple[BrokerPosition, ...],
    completed_at: datetime,
    broker_account_id: str = "paper-account-unavailable-in-pure-evaluation",
    startup_steps: tuple[str, ...] = STARTUP_SEQUENCE,
    initial_discrepancy_codes: tuple[str, ...] = (),
) -> ReconciliationResult:
    """Classify discrepancies without mutating either source of truth."""

    local_latest = _latest_orders(local_orders)
    broker_latest = _latest_orders(broker_orders)
    local_by_symbol = {item.symbol: item for item in local_positions}
    broker_by_symbol = {item.symbol: item for item in broker_positions}
    blocking = list(initial_discrepancy_codes)
    recoverable: list[str] = []
    explained_broker_positions: set[str] = set()

    for key, broker_order in broker_latest.items():
        local_order = local_latest.get(key)
        if local_order is None:
            blocking.append("UNKNOWN_BROKER_ORDER")
            continue
        if (
            local_order.symbol != broker_order.symbol
            or local_order.side != broker_order.side
            or local_order.quantity != broker_order.quantity
        ):
            blocking.append("ORDER_IDENTITY_MISMATCH")
        elif local_order.status != broker_order.status:
            if local_order.status in _OPEN_STATUSES and broker_order.status == "filled":
                recoverable.append("LOCAL_ORDER_STATUS_STALE")
            else:
                blocking.append("ORDER_STATUS_MISMATCH")

    for key, local_order in local_latest.items():
        if local_order.status not in _OPEN_STATUSES or key in broker_latest:
            continue
        broker_position = broker_by_symbol.get(local_order.symbol)
        local_position = local_by_symbol.get(local_order.symbol)
        local_quantity = 0 if local_position is None else local_position.quantity
        expected_quantity = local_quantity + local_order.quantity - local_order.filled_quantity
        if (
            local_order.side == "buy"
            and broker_position is not None
            and broker_position.quantity == expected_quantity
        ):
            recoverable.append("PENDING_ENTRY_FILLED_AT_BROKER")
            explained_broker_positions.add(local_order.symbol)
        else:
            blocking.append("LOCAL_OPEN_ORDER_MISSING_AT_BROKER")

    for symbol in sorted(set(local_by_symbol) | set(broker_by_symbol)):
        local_position = local_by_symbol.get(symbol)
        broker_position = broker_by_symbol.get(symbol)
        if local_position is None and broker_position is not None:
            if symbol not in explained_broker_positions:
                blocking.append("BROKER_POSITION_MISSING_LOCALLY")
        elif local_position is not None and broker_position is None:
            blocking.append("LOCAL_POSITION_MISSING_AT_BROKER")
        elif (
            local_position is not None
            and broker_position is not None
            and local_position.quantity != broker_position.quantity
        ):
            blocking.append("POSITION_QUANTITY_MISMATCH")

    blocking_codes = tuple(sorted(set(blocking)))
    recoverable_codes = tuple(sorted(set(recoverable)))
    status: Literal["clean", "recoverable", "blocked"] = (
        "blocked" if blocking_codes else "recoverable" if recoverable_codes else "clean"
    )
    discrepancies = blocking_codes if blocking_codes else recoverable_codes
    local_hash = _evidence_hash(
        tuple(local_latest[key] for key in sorted(local_latest)),
        tuple(local_by_symbol[key] for key in sorted(local_by_symbol)),
    )
    broker_hash = _evidence_hash(
        tuple(broker_latest[key] for key in sorted(broker_latest)),
        tuple(broker_by_symbol[key] for key in sorted(broker_by_symbol)),
    )
    identity = {
        "broker_state_sha256": broker_hash,
        "completed_at": completed_at.isoformat(),
        "discrepancy_codes": discrepancies,
        "local_state_sha256": local_hash,
        "paper_session_id": paper_session_id,
        "status": status,
    }
    reconciliation_id = (
        "reconciliation-" + hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()
    )
    return ReconciliationResult(
        reconciliation_id=reconciliation_id,
        paper_session_id=paper_session_id,
        status=status,
        entries_enabled=status == "clean",
        exits_enabled=True,
        discrepancy_codes=discrepancies,
        startup_steps=startup_steps,
        broker_account_id=broker_account_id,
        local_state_sha256=local_hash,
        broker_state_sha256=broker_hash,
        completed_at=completed_at,
    )


def run_startup_reconciliation(
    *,
    store: PaperStore,
    broker: PaperBroker,
    paper_session_id: str,
    completed_at: datetime,
) -> ReconciliationResult:
    """Run the audited startup sequence and persist the comparison once."""

    required_tables = {
        "paper_sessions",
        "order_intents",
        "order_events",
        "position_snapshots",
        "reconciliation_runs",
    }
    if not required_tables <= set(store.table_names()):
        raise RuntimeError("PAPER_SCHEMA_INCOMPLETE")
    session = store.get_session(paper_session_id)
    if session is None:
        raise RuntimeError("PAPER_SESSION_NOT_FOUND")
    broker.clock()
    account = broker.account()
    broker_orders = broker.open_orders()
    broker_positions = broker.positions()
    local_orders = store.list_order_events(paper_session_id)
    snapshots = store.list_position_snapshots(paper_session_id)
    local_positions = () if not snapshots else snapshots[-1].positions
    initial_codes = (
        ("BROKER_ACCOUNT_MISMATCH",) if account.account_id != session.broker_account_id else ()
    )
    result = evaluate_reconciliation(
        paper_session_id=paper_session_id,
        local_orders=local_orders,
        local_positions=local_positions,
        broker_orders=broker_orders,
        broker_positions=broker_positions,
        completed_at=completed_at,
        broker_account_id=account.account_id,
        startup_steps=STARTUP_SEQUENCE,
        initial_discrepancy_codes=initial_codes,
    )
    return store.append_reconciliation(result)
