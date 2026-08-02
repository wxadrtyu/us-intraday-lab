"""Deterministic paper-state replay and restart-safe order key derivation."""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

from us_intraday_lab.contracts.market import MarketBarClosed
from us_intraday_lab.contracts.paper import BrokerOrder, PositionSnapshot
from us_intraday_lab.paper.store import PaperStore


class RecoveryIntegrityError(RuntimeError):
    """Stored checkpoint evidence cannot reproduce the claimed state."""


@dataclass(frozen=True, slots=True)
class RecoveredPaperState:
    paper_session_id: str
    processed_provider_event_ids: tuple[str, ...]
    latest_orders: tuple[tuple[str, str, int], ...]
    positions: tuple[tuple[str, int], ...]
    last_event_at: datetime | None

    @property
    def content_sha256(self) -> str:
        payload = {
            "last_event_at": (
                None if self.last_event_at is None else self.last_event_at.isoformat()
            ),
            "latest_orders": self.latest_orders,
            "paper_session_id": self.paper_session_id,
            "positions": self.positions,
            "processed_provider_event_ids": self.processed_provider_event_ids,
        }
        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class RecoveryResult:
    state: RecoveredPaperState
    resumed_from_checkpoint_id: str | None
    replayed_after_checkpoint: int
    clean_replay_sha256: str


@dataclass(frozen=True, slots=True)
class _ReplayEvent:
    occurred_at: datetime
    kind: Literal["market", "order", "position"]
    identity: str
    payload: object


def _events(
    *,
    market_events: tuple[MarketBarClosed, ...],
    order_events: tuple[BrokerOrder, ...],
    position_snapshots: tuple[PositionSnapshot, ...],
) -> tuple[_ReplayEvent, ...]:
    rows = [
        _ReplayEvent(item.available_at, "market", item.provider_event_id, item)
        for item in market_events
    ]
    rows.extend(
        _ReplayEvent(item.updated_at, "order", item.client_order_id, item) for item in order_events
    )
    rows.extend(
        _ReplayEvent(item.observed_at, "position", item.snapshot_id, item)
        for item in position_snapshots
    )
    kind_order = {"market": 0, "order": 1, "position": 2}
    return tuple(
        sorted(rows, key=lambda item: (item.occurred_at, kind_order[item.kind], item.identity))
    )


def _apply_events(
    *,
    paper_session_id: str,
    events: tuple[_ReplayEvent, ...],
    initial: RecoveredPaperState | None = None,
) -> RecoveredPaperState:
    provider_ids = [] if initial is None else list(initial.processed_provider_event_ids)
    seen_provider_ids = set(provider_ids)
    orders = {} if initial is None else {item[0]: item[1:] for item in initial.latest_orders}
    positions = {} if initial is None else dict(initial.positions)
    last_event_at = None if initial is None else initial.last_event_at
    for event in events:
        if event.kind == "market":
            market = event.payload
            if not isinstance(market, MarketBarClosed):
                raise TypeError("market replay payload is invalid")
            if market.provider_event_id not in seen_provider_ids:
                seen_provider_ids.add(market.provider_event_id)
                provider_ids.append(market.provider_event_id)
        elif event.kind == "order":
            order = event.payload
            if not isinstance(order, BrokerOrder):
                raise TypeError("order replay payload is invalid")
            orders[order.client_order_id] = (order.status, order.filled_quantity)
        else:
            snapshot = event.payload
            if not isinstance(snapshot, PositionSnapshot):
                raise TypeError("position replay payload is invalid")
            positions = {item.symbol: item.quantity for item in snapshot.positions}
        last_event_at = event.occurred_at
    return RecoveredPaperState(
        paper_session_id=paper_session_id,
        processed_provider_event_ids=tuple(provider_ids),
        latest_orders=tuple((key, value[0], value[1]) for key, value in sorted(orders.items())),
        positions=tuple(sorted(positions.items())),
        last_event_at=last_event_at,
    )


def replay_evidence(
    *,
    paper_session_id: str,
    market_events: tuple[MarketBarClosed, ...],
    order_events: tuple[BrokerOrder, ...],
    position_snapshots: tuple[PositionSnapshot, ...],
) -> RecoveredPaperState:
    """Rebuild state from immutable evidence in deterministic causal order."""

    return _apply_events(
        paper_session_id=paper_session_id,
        events=_events(
            market_events=market_events,
            order_events=order_events,
            position_snapshots=position_snapshots,
        ),
    )


def recover_session(*, store: PaperStore, paper_session_id: str) -> RecoveryResult:
    market_records = store.list_market_replay_records(paper_session_id)
    order_records = store.list_order_replay_records(paper_session_id)
    position_records = store.list_position_replay_records(paper_session_id)
    all_events = _events(
        market_events=tuple(item.event for item in market_records),
        order_events=tuple(item.event for item in order_records),
        position_snapshots=tuple(item.snapshot for item in position_records),
    )
    clean = _apply_events(paper_session_id=paper_session_id, events=all_events)
    checkpoint = store.latest_checkpoint(paper_session_id)
    if checkpoint is None:
        return RecoveryResult(
            state=clean,
            resumed_from_checkpoint_id=None,
            replayed_after_checkpoint=len(all_events),
            clean_replay_sha256=clean.content_sha256,
        )
    prefix_events = _events(
        market_events=tuple(
            item.event
            for item in market_records
            if item.checkpoint_base_sequence < checkpoint.event_sequence
        ),
        order_events=tuple(
            item.event
            for item in order_records
            if item.checkpoint_sequence <= checkpoint.event_sequence
        ),
        position_snapshots=tuple(
            item.snapshot
            for item in position_records
            if item.checkpoint_base_sequence < checkpoint.event_sequence
        ),
    )
    prefix = _apply_events(paper_session_id=paper_session_id, events=prefix_events)
    if prefix.content_sha256 != checkpoint.state_sha256:
        raise RecoveryIntegrityError("CHECKPOINT_STATE_HASH_MISMATCH")
    later_events = _events(
        market_events=tuple(
            item.event
            for item in market_records
            if item.checkpoint_base_sequence >= checkpoint.event_sequence
        ),
        order_events=tuple(
            item.event
            for item in order_records
            if item.checkpoint_sequence > checkpoint.event_sequence
        ),
        position_snapshots=tuple(
            item.snapshot
            for item in position_records
            if item.checkpoint_base_sequence >= checkpoint.event_sequence
        ),
    )
    resumed = _apply_events(
        paper_session_id=paper_session_id,
        events=later_events,
        initial=prefix,
    )
    if resumed.content_sha256 != clean.content_sha256:
        raise RecoveryIntegrityError("RESUMED_STATE_DIFFERS_FROM_CLEAN_REPLAY")
    return RecoveryResult(
        state=resumed,
        resumed_from_checkpoint_id=checkpoint.checkpoint_id,
        replayed_after_checkpoint=len(later_events),
        clean_replay_sha256=clean.content_sha256,
    )


def build_order_idempotency_key(
    *,
    paper_session_id: str,
    strategy_id: str,
    symbol: str,
    signal_available_at: datetime,
    action: Literal["entry", "exit"],
    entry_sequence: int,
) -> str:
    if type(paper_session_id) is not str or not paper_session_id:
        raise ValueError("paper_session_id must be a non-empty exact string")
    if type(strategy_id) is not str or not strategy_id:
        raise ValueError("strategy_id must be a non-empty exact string")
    if type(symbol) is not str or symbol not in {"SPY", "QQQ", "IWM"}:
        raise ValueError("symbol must be a production symbol")
    if type(signal_available_at) is not datetime:
        raise TypeError("signal_available_at must be an exact datetime")
    if signal_available_at.utcoffset() != timedelta(0):
        raise ValueError("signal_available_at must be timezone-aware UTC")
    if type(action) is not str or action not in {"entry", "exit"}:
        raise ValueError("action must be entry or exit")
    if type(entry_sequence) is not int or not 1 <= entry_sequence <= 3:
        raise ValueError("entry_sequence must be between 1 and 3")
    payload = {
        "action": action,
        "entry_sequence": entry_sequence,
        "paper_session_id": paper_session_id,
        "signal_available_at": signal_available_at.astimezone(UTC).isoformat(),
        "strategy_id": strategy_id,
        "symbol": symbol,
    }
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).digest()
    return "po_" + base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
