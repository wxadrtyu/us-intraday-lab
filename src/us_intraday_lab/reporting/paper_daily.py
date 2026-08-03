"""Render a Chinese daily paper report from durable broker evidence only."""

from __future__ import annotations

import os
import tempfile
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from us_intraday_lab.contracts.orders import OrderIntent
from us_intraday_lab.contracts.paper import BrokerOrder
from us_intraday_lab.contracts.registry import RegistryEvent, RegistryState
from us_intraday_lab.paper.sizing import SizingRequest, replay_balance_feasibility
from us_intraday_lab.paper.store import PaperStore
from us_intraday_lab.registry.store import RegistryStore

_TEMPLATE_DIRECTORY = Path(__file__).with_name("templates")
_ACTIVE_STATES: tuple[RegistryState, ...] = (
    "paper_observing",
    "paper_ranked",
    "leader",
)


@dataclass(frozen=True, slots=True)
class ClosedPaperTrade:
    strategy_id: str
    symbol: str
    session_date: date
    quantity: int
    entry_price: float
    exit_price: float
    pnl: float
    entry_order_id: str
    exit_order_id: str


def _latest_orders(events: tuple[BrokerOrder, ...]) -> dict[str, BrokerOrder]:
    latest: dict[str, BrokerOrder] = {}
    for event in events:
        retained = latest.get(event.client_order_id)
        if retained is None or event.updated_at >= retained.updated_at:
            latest[event.client_order_id] = event
    return latest


def closed_trades_from_store(
    store: PaperStore,
    paper_session_id: str,
    *,
    strategy_id: str | None = None,
) -> tuple[ClosedPaperTrade, ...]:
    """FIFO-match stored broker fills; never infer a fill from market bars."""

    session = store.get_session(paper_session_id)
    if session is None:
        raise ValueError("PAPER_SESSION_NOT_FOUND")
    intents = store.list_order_intents(paper_session_id)
    latest = _latest_orders(store.list_order_events(paper_session_id))
    lots: dict[tuple[str, str], deque[tuple[int, float, str]]] = defaultdict(deque)
    closed: list[ClosedPaperTrade] = []
    for intent in intents:
        if strategy_id is not None and intent.strategy_id != strategy_id:
            continue
        order = latest.get(intent.idempotency_key)
        if order is None or order.filled_quantity == 0 or order.average_fill_price is None:
            continue
        key = (intent.strategy_id, intent.symbol)
        remaining = order.filled_quantity
        if intent.side == "buy":
            lots[key].append((remaining, order.average_fill_price, order.broker_order_id))
            continue
        while remaining and lots[key]:
            entry_quantity, entry_price, entry_order_id = lots[key].popleft()
            matched = min(remaining, entry_quantity)
            closed.append(
                ClosedPaperTrade(
                    strategy_id=intent.strategy_id,
                    symbol=intent.symbol,
                    session_date=session.session_date,
                    quantity=matched,
                    entry_price=entry_price,
                    exit_price=order.average_fill_price,
                    pnl=(order.average_fill_price - entry_price) * matched,
                    entry_order_id=entry_order_id,
                    exit_order_id=order.broker_order_id,
                )
            )
            remaining -= matched
            if entry_quantity > matched:
                lots[key].appendleft((entry_quantity - matched, entry_price, entry_order_id))
    return tuple(closed)


def _max_drawdown(trades: tuple[ClosedPaperTrade, ...]) -> float:
    cumulative = 0.0
    peak = 0.0
    drawdown = 0.0
    for trade in trades:
        cumulative += trade.pnl
        peak = max(peak, cumulative)
        drawdown = max(drawdown, peak - cumulative)
    return drawdown


def _slippage_rows(
    intents: tuple[OrderIntent, ...], latest: dict[str, BrokerOrder]
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for intent in intents:
        order = latest.get(intent.idempotency_key)
        if order is None or order.average_fill_price is None:
            continue
        slippage_bps: float | None = None
        if intent.limit_price is not None:
            direction = 1.0 if intent.side == "buy" else -1.0
            slippage_bps = (
                direction
                * (order.average_fill_price - intent.limit_price)
                / intent.limit_price
                * 10_000
            )
        rows.append(
            {
                "strategy_id": intent.strategy_id,
                "symbol": intent.symbol,
                "side": intent.side,
                "status": order.status,
                "filled_quantity": order.filled_quantity,
                "fill_price": order.average_fill_price,
                "slippage_bps": slippage_bps,
                "broker_order_id": order.broker_order_id,
            }
        )
    return tuple(rows)


def _feasibility(
    intents: tuple[OrderIntent, ...],
    latest: dict[str, BrokerOrder],
    registry: RegistryStore,
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for intent in intents:
        if intent.side != "buy" or intent.strategy_id in seen:
            continue
        order = latest.get(intent.idempotency_key)
        definition = registry.get_strategy_definition(intent.strategy_id)
        if order is None or order.average_fill_price is None or definition is None:
            continue
        seen.add(intent.strategy_id)
        price = order.average_fill_price
        diagnostics = replay_balance_feasibility(
            SizingRequest(
                available_cash=25_000.0,
                account_equity=25_000.0,
                reference_price=price,
                stop_distance=price * definition.risk.stop_loss_bps / 10_000,
                strategy_risk_fraction=0.005,
                max_position_fraction=0.25,
            )
        )
        rows.append(
            {
                "strategy_id": intent.strategy_id,
                "symbol": intent.symbol,
                "reference_price": price,
                "balances": diagnostics,
            }
        )
    return tuple(rows)


def daily_report_context(
    *, paper_store: PaperStore, registry_store: RegistryStore, session_date: date
) -> dict[str, Any]:
    """Load and reconcile one deterministic report snapshot from stored evidence."""

    sessions = tuple(
        item for item in paper_store.list_sessions() if item.session_date == session_date
    )
    if len(sessions) != 1:
        raise ValueError("PAPER_SESSION_DATE_NOT_UNIQUE")
    session = sessions[0]
    intents = paper_store.list_order_intents(session.paper_session_id)
    order_events = paper_store.list_order_events(session.paper_session_id)
    latest = _latest_orders(order_events)
    trades = closed_trades_from_store(paper_store, session.paper_session_id)
    snapshots = paper_store.list_position_snapshots(session.paper_session_id)
    if not snapshots:
        raise ValueError("FINAL_POSITION_SNAPSHOT_REQUIRED")
    final_snapshot = snapshots[-1]
    incidents = paper_store.list_incidents(session.paper_session_id)
    reconciliations = paper_store.list_reconciliation_runs(session.paper_session_id)
    all_trades = tuple(
        trade
        for stored_session in paper_store.list_sessions()
        if stored_session.session_date <= session_date
        for trade in closed_trades_from_store(paper_store, stored_session.paper_session_id)
    )
    strategy_ids = sorted({intent.strategy_id for intent in intents})
    strategy_rows = []
    lifecycle_changes: list[RegistryEvent] = []
    for retained_strategy_id in strategy_ids:
        strategy_trades = tuple(
            trade for trade in trades if trade.strategy_id == retained_strategy_id
        )
        events = registry_store.list_events(retained_strategy_id)
        lifecycle_changes.extend(
            event for event in events if event.occurred_at.date() == session_date
        )
        ranked = next(
            (event for event in reversed(events) if "quality_score" in event.immutable_refs),
            None,
        )
        strategy_rows.append(
            {
                "strategy_id": retained_strategy_id,
                "state": registry_store.get_current_state(retained_strategy_id),
                "trade_count": len(strategy_trades),
                "pnl": sum(trade.pnl for trade in strategy_trades),
                "quality_score": (
                    None if ranked is None else ranked.immutable_refs["quality_score"]
                ),
                "rank": None if ranked is None else ranked.immutable_refs["rank"],
            }
        )
    active = registry_store.list_strategy_definitions_in_states(_ACTIVE_STATES)
    active_by_state = {
        state: tuple(
            definition.strategy_id for definition, item_state in active if item_state == state
        )
        for state in _ACTIVE_STATES
    }
    pnl_by_symbol = {
        symbol: sum(trade.pnl for trade in trades if trade.symbol == symbol)
        for symbol in ("SPY", "QQQ", "IWM")
    }
    return {
        "session": session,
        "paper_session_id": session.paper_session_id,
        "session_date": session.session_date,
        "account_id": session.broker_account_id,
        "status": session.status,
        "daily_pnl": sum(trade.pnl for trade in trades),
        "cumulative_pnl": sum(trade.pnl for trade in all_trades),
        "max_drawdown": _max_drawdown(trades),
        "closed_trade_count": len(trades),
        "order_count": len(intents),
        "filled_order_count": sum(order.filled_quantity > 0 for order in latest.values()),
        "rejected_order_count": sum(order.status == "rejected" for order in latest.values()),
        "final_positions": final_snapshot.positions,
        "flat_at_close": not final_snapshot.positions,
        "order_rows": _slippage_rows(intents, latest),
        "slippage_available_count": sum(intent.limit_price is not None for intent in intents),
        "strategy_rows": tuple(strategy_rows),
        "lifecycle_changes": tuple(
            sorted(lifecycle_changes, key=lambda event: (event.occurred_at, event.event_id))
        ),
        "active_by_state": active_by_state,
        "market_event_count": len(paper_store.list_market_events(session.paper_session_id)),
        "reconciliation_status": ("missing" if not reconciliations else reconciliations[-1].status),
        "incidents": incidents,
        "pnl_by_symbol": pnl_by_symbol,
        "feasibility_rows": _feasibility(intents, latest, registry_store),
        "evidence_order_ids": tuple(sorted(order.broker_order_id for order in latest.values())),
    }


def _write_rendered(destination: Path, rendered: str) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_path = tempfile.mkstemp(
        prefix=f".{destination.stem}-", suffix=".tmp", dir=destination.parent
    )
    temporary = Path(raw_path)
    try:
        with os.fdopen(descriptor, "wb") as target:
            target.write(rendered.encode("utf-8"))
            target.flush()
            os.fsync(target.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


def render_paper_daily_report(
    *, root: Path, paper_store: PaperStore, registry_store: RegistryStore, session_date: date
) -> Path:
    if not isinstance(root, Path) or not root.is_dir():
        raise ValueError("root must be an existing directory")
    environment = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIRECTORY),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    context = daily_report_context(
        paper_store=paper_store, registry_store=registry_store, session_date=session_date
    )
    rendered = environment.get_template("paper_daily_zh.md.j2").render(**context)
    return _write_rendered(
        root / "reports" / "generated" / "paper" / f"{session_date.isoformat()}.md",
        rendered,
    )
