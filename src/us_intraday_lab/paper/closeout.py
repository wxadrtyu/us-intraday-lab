"""Fail-closed end-of-day liquidation orchestration."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from us_intraday_lab.contracts.orders import OrderIntent
from us_intraday_lab.contracts.paper import (
    BrokerOrder,
    BrokerPosition,
    IncidentEvent,
    PaperCheckpoint,
    PositionSnapshot,
    RiskDecision,
)
from us_intraday_lab.paper.broker import PaperBroker
from us_intraday_lab.paper.recovery import replay_evidence
from us_intraday_lab.paper.store import PaperStore


@dataclass(frozen=True, slots=True)
class CloseoutResult:
    entries_enabled: bool
    clean: bool
    status: Literal["closed", "blocked"]
    cancelled_broker_order_ids: tuple[str, ...]
    exit_idempotency_keys: tuple[str, ...]
    remaining_positions: tuple[BrokerPosition, ...]
    incident: IncidentEvent | None


def _digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _snapshot(
    *,
    paper_session_id: str,
    positions: tuple[BrokerPosition, ...],
    observed_at: datetime,
    phase: str,
) -> PositionSnapshot:
    digest = _digest(
        {
            "paper_session_id": paper_session_id,
            "phase": phase,
            "positions": [(item.symbol, item.quantity) for item in positions],
            "observed_at": observed_at.isoformat(),
        }
    )
    return PositionSnapshot(
        snapshot_id=f"closeout-{phase}-{digest[:24]}",
        paper_session_id=paper_session_id,
        positions=positions,
        observed_at=observed_at,
    )


def _exit_key(*, paper_session_id: str, symbol: str) -> str:
    return "po_close_" + _digest(
        {"paper_session_id": paper_session_id, "symbol": symbol, "action": "exit"}
    )[:32]


def _exit_intent(
    *,
    paper_session_id: str,
    session_date: date,
    strategy_id: str,
    position: BrokerPosition,
    closeout_at: datetime,
) -> OrderIntent:
    return OrderIntent(
        schema_version="1.0.0",
        run_id=paper_session_id,
        strategy_id=strategy_id,
        symbol=position.symbol,
        session=session_date,
        side="sell",
        order_type="market",
        quantity=position.quantity,
        signal_time=closeout_at,
        eligible_time=closeout_at,
        reason_code="session_close",
        idempotency_key=_exit_key(
            paper_session_id=paper_session_id,
            symbol=position.symbol,
        ),
    )


def _record_exit(
    *,
    store: PaperStore,
    intent: OrderIntent,
    broker_order: BrokerOrder,
    closeout_at: datetime,
) -> None:
    decision = RiskDecision(
        decision_id="closeout-risk-" + _digest(intent.idempotency_key)[:24],
        idempotency_key=intent.idempotency_key,
        approved=True,
        reason_code="CLOSEOUT_EXIT_REQUIRED",
        observed_values={
            "symbol": intent.symbol,
            "quantity": intent.quantity,
            "long_only_exit": True,
        },
        decided_at=closeout_at,
    )
    state = replay_evidence(
        paper_session_id=intent.run_id,
        market_events=store.list_market_events(intent.run_id),
        order_events=store.list_order_events(intent.run_id) + (broker_order,),
        position_snapshots=store.list_position_snapshots(intent.run_id),
    )
    latest = store.latest_checkpoint(intent.run_id)
    sequence = 1 if latest is None else latest.event_sequence + 1
    checkpoint = PaperCheckpoint(
        checkpoint_id=f"closeout-checkpoint-{sequence}-{state.content_sha256[:16]}",
        paper_session_id=intent.run_id,
        event_sequence=sequence,
        state_sha256=state.content_sha256,
        created_at=max(closeout_at, broker_order.updated_at),
    )
    store.record_order_bundle(
        intent=intent,
        risk_decision=decision,
        broker_order=broker_order,
        checkpoint=checkpoint,
    )


def closeout_session(
    *,
    broker: PaperBroker,
    store: PaperStore,
    paper_session_id: str,
    strategy_ids_by_symbol: Mapping[str, str],
    closeout_at: datetime,
    max_cancel_polls: int,
    max_exit_attempts: int,
    max_flat_polls: int,
) -> CloseoutResult:
    """Cancel entries, liquidate longs, verify flatness, and persist evidence."""

    if min(max_cancel_polls, max_exit_attempts, max_flat_polls) < 1:
        raise ValueError("closeout poll and attempt limits must be positive")
    session = store.get_session(paper_session_id)
    if session is None:
        raise ValueError("PAPER_SESSION_NOT_FOUND")
    store.transition_session_status(paper_session_id, "closeout")

    cancelled: list[str] = []
    for _ in range(max_cancel_polls):
        opening_orders = tuple(item for item in broker.open_orders() if item.side == "buy")
        if not opening_orders:
            break
        for order in opening_orders:
            broker.cancel(order.broker_order_id)
            if order.broker_order_id not in cancelled:
                cancelled.append(order.broker_order_id)

    starting_positions = broker.positions()
    store.append_position_snapshot(
        _snapshot(
            paper_session_id=paper_session_id,
            positions=starting_positions,
            observed_at=closeout_at,
            phase="start",
        )
    )

    exit_keys: list[str] = []
    for position in starting_positions:
        intent = _exit_intent(
            paper_session_id=paper_session_id,
            session_date=session.session_date,
            strategy_id=strategy_ids_by_symbol.get(
                position.symbol, "paper-account-closeout"
            ),
            position=position,
            closeout_at=closeout_at,
        )
        exit_keys.append(intent.idempotency_key)
        first_order: BrokerOrder | None = None
        for _ in range(max_exit_attempts):
            response = broker.submit(intent)
            if first_order is None:
                first_order = response
                _record_exit(
                    store=store,
                    intent=intent,
                    broker_order=response,
                    closeout_at=closeout_at,
                )
            if response.status != "rejected":
                break

    remaining = broker.positions()
    for _ in range(max_flat_polls - 1):
        if not remaining:
            break
        remaining = broker.positions()

    final_snapshot = _snapshot(
        paper_session_id=paper_session_id,
        positions=remaining,
        observed_at=closeout_at,
        phase="final",
    )
    store.append_position_snapshot(final_snapshot)
    pending_opening = tuple(item for item in broker.open_orders() if item.side == "buy")
    clean = not remaining and not pending_opening

    incident: IncidentEvent | None = None
    if not clean:
        remaining_symbols = ",".join(item.symbol for item in remaining)
        pending_ids = ",".join(item.broker_order_id for item in pending_opening)
        incident = IncidentEvent(
            incident_id="overnight-risk-"
            + _digest(
                {
                    "paper_session_id": paper_session_id,
                    "remaining": [(item.symbol, item.quantity) for item in remaining],
                    "pending_opening_order_ids": pending_ids,
                }
            )[:24],
            paper_session_id=paper_session_id,
            severity="critical",
            reason_code="OVERNIGHT_RISK_INCIDENT",
            observed_values={
                "remaining_position_count": len(remaining),
                "remaining_symbols": remaining_symbols,
                "pending_opening_order_ids": pending_ids,
                "flat": False,
            },
            occurred_at=closeout_at,
        )
        store.append_incident(incident)

    store.transition_session_status(
        paper_session_id,
        "closed" if clean else "blocked",
    )

    return CloseoutResult(
        entries_enabled=False,
        clean=clean,
        status="closed" if clean else "blocked",
        cancelled_broker_order_ids=tuple(cancelled),
        exit_idempotency_keys=tuple(exit_keys),
        remaining_positions=remaining,
        incident=incident,
    )
