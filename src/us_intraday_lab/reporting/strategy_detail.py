"""Render one Chinese strategy evidence dossier."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from us_intraday_lab.contracts.paper import IncidentEvent
from us_intraday_lab.paper.store import PaperStore
from us_intraday_lab.registry.store import RegistryStore
from us_intraday_lab.reporting.paper_daily import (
    _TEMPLATE_DIRECTORY,
    ClosedPaperTrade,
    _write_rendered,
    closed_trades_from_store,
)


def _stored_json(refs: object, name: str) -> dict[str, float]:
    if not isinstance(refs, dict) or name not in refs:
        return {}
    decoded = json.loads(str(refs[name]))
    if not isinstance(decoded, dict) or any(
        not isinstance(key, str) or not isinstance(value, (int, float))
        for key, value in decoded.items()
    ):
        raise ValueError(f"INVALID_STORED_RANKING_{name.upper()}")
    return {key: float(value) for key, value in decoded.items()}


def strategy_report_context(
    *, paper_store: PaperStore, registry_store: RegistryStore, strategy_id: str
) -> dict[str, Any]:
    definition = registry_store.get_strategy_definition(strategy_id)
    if definition is None:
        raise ValueError("STRATEGY_NOT_REGISTERED")
    lifecycle_events = registry_store.list_events(strategy_id)
    decision_ids = tuple(
        event.immutable_refs["decision_id"]
        for event in lifecycle_events
        if "decision_id" in event.immutable_refs
    )
    decisions = tuple(
        decision
        for decision_id in dict.fromkeys(decision_ids)
        if (decision := registry_store.get_validation_decision(decision_id)) is not None
    )
    ranking_event = next(
        (
            event
            for event in reversed(lifecycle_events)
            if "component_values" in event.immutable_refs
        ),
        None,
    )
    ranking_refs = {} if ranking_event is None else dict(ranking_event.immutable_refs)

    session_rows = []
    all_trades: list[ClosedPaperTrade] = []
    all_incidents: list[IncidentEvent] = []
    slippages: list[float] = []
    for session in paper_store.list_sessions():
        intents = tuple(
            item
            for item in paper_store.list_order_intents(session.paper_session_id)
            if item.strategy_id == strategy_id
        )
        if not intents:
            continue
        trades = closed_trades_from_store(
            paper_store, session.paper_session_id, strategy_id=strategy_id
        )
        all_trades.extend(trades)
        all_incidents.extend(paper_store.list_incidents(session.paper_session_id))
        order_by_key = {
            order.client_order_id: order
            for order in paper_store.list_order_events(session.paper_session_id)
        }
        for intent in intents:
            order = order_by_key.get(intent.idempotency_key)
            if (
                order is not None
                and order.average_fill_price is not None
                and intent.limit_price is not None
            ):
                direction = 1.0 if intent.side == "buy" else -1.0
                slippages.append(
                    direction
                    * (order.average_fill_price - intent.limit_price)
                    / intent.limit_price
                    * 10_000
                )
        session_rows.append(
            {
                "date": session.session_date,
                "status": session.status,
                "orders": len(intents),
                "closed_trades": len(trades),
                "pnl": sum(trade.pnl for trade in trades),
            }
        )
    pnl_by_symbol = {
        symbol: sum(trade.pnl for trade in all_trades if trade.symbol == symbol)
        for symbol in definition.symbols
    }
    pnl_by_day: dict[date, float] = defaultdict(float)
    for trade in all_trades:
        pnl_by_day[trade.session_date] += trade.pnl
    first_day = None if not session_rows else min(item["date"] for item in session_rows)
    last_day = None if not session_rows else max(item["date"] for item in session_rows)
    return {
        "strategy_id": strategy_id,
        "current_state": registry_store.get_current_state(strategy_id),
        "definition_json": definition.model_dump_json(indent=2),
        "decisions": decisions,
        "paper_first_day": first_day,
        "paper_last_day": last_day,
        "paper_completed_days": len(
            {item["date"] for item in session_rows if item["status"] == "closed"}
        ),
        "closed_trade_count": len(all_trades),
        "total_pnl": sum(trade.pnl for trade in all_trades),
        "session_rows": tuple(session_rows),
        "pnl_by_symbol": pnl_by_symbol,
        "pnl_by_day": tuple(sorted(pnl_by_day.items())),
        "execution_slippage_bps": (None if not slippages else sum(slippages) / len(slippages)),
        "forward_component_values": _stored_json(ranking_refs, "component_values"),
        "forward_component_scores": _stored_json(ranking_refs, "component_scores"),
        "forward_weights": _stored_json(ranking_refs, "ranking_weights"),
        "forward_rank": ranking_refs.get("rank"),
        "forward_quality_score": ranking_refs.get("quality_score"),
        "historical_divergence": _stored_json(ranking_refs, "component_values").get(
            "historical_divergence"
        ),
        "lifecycle_events": lifecycle_events,
        "incidents": tuple(all_incidents),
    }


def render_strategy_detail_report(
    *, root: Path, paper_store: PaperStore, registry_store: RegistryStore, strategy_id: str
) -> Path:
    if not isinstance(root, Path) or not root.is_dir():
        raise ValueError("root must be an existing directory")
    environment = Environment(
        loader=FileSystemLoader(_TEMPLATE_DIRECTORY),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    rendered = environment.get_template("strategy_detail_zh.md.j2").render(
        **strategy_report_context(
            paper_store=paper_store,
            registry_store=registry_store,
            strategy_id=strategy_id,
        )
    )
    safe_name = quote(strategy_id, safe="-_.@")
    return _write_rendered(
        root / "reports" / "generated" / "strategies" / f"{safe_name}.md",
        rendered,
    )
