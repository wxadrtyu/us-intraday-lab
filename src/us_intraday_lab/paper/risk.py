"""Ordered, auditable entry-risk gates for paper execution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from us_intraday_lab.contracts.orders import OrderIntent
from us_intraday_lab.contracts.paper import RiskDecision
from us_intraday_lab.paper.sizing import SizingResult

PRODUCTION_SYMBOLS = frozenset({"SPY", "QQQ", "IWM"})
ENABLED_PAPER_STATES = frozenset({"paper_shadow", "paper_observing", "paper_ranked", "leader"})


@dataclass(frozen=True, slots=True)
class RiskContext:
    intent: OrderIntent
    decided_at: datetime
    regular_open: datetime
    regular_close: datetime
    closeout_buffer: timedelta
    feed_observed_at: datetime
    broker_clock_observed_at: datetime
    max_feed_age: timedelta
    max_broker_clock_age: timedelta
    reconciliation_status: Literal["clean", "recoverable", "blocked"]
    storage_circuit_open: bool
    account_position_count: int
    strategy_entry_count: int
    strategy_state: str
    available_cash: float
    account_multiplier: int
    sizing: SizingResult
    daily_loss: float
    daily_loss_limit: float
    account_loss: float
    account_loss_limit: float
    strategy_loss: float
    strategy_loss_limit: float
    duplicate_intent: bool
    conflicting_intent: bool


Observed = dict[str, float | int | bool | str]


def _base_observed(context: RiskContext) -> Observed:
    feed_age = (context.decided_at - context.feed_observed_at).total_seconds()
    clock_age = (context.decided_at - context.broker_clock_observed_at).total_seconds()
    closeout_at = context.regular_close - context.closeout_buffer
    return {
        "symbol": context.intent.symbol,
        "side": context.intent.side,
        "decided_at": context.decided_at.isoformat(),
        "regular_open": context.regular_open.isoformat(),
        "regular_close": context.regular_close.isoformat(),
        "closeout_at": closeout_at.isoformat(),
        "feed_age_seconds": feed_age,
        "max_feed_age_seconds": context.max_feed_age.total_seconds(),
        "broker_clock_age_seconds": clock_age,
        "max_broker_clock_age_seconds": context.max_broker_clock_age.total_seconds(),
        "reconciliation_status": context.reconciliation_status,
        "storage_circuit_open": context.storage_circuit_open,
        "account_position_count": context.account_position_count,
        "strategy_entry_count": context.strategy_entry_count,
        "strategy_state": context.strategy_state,
        "available_cash": context.available_cash,
        "account_multiplier": context.account_multiplier,
        "sizing_reason": context.sizing.reason_code,
        "sized_quantity": context.sizing.quantity,
        "requested_quantity": context.intent.quantity,
        "required_cash": context.sizing.required_cash,
        "daily_loss": context.daily_loss,
        "daily_loss_limit": context.daily_loss_limit,
        "account_loss": context.account_loss,
        "account_loss_limit": context.account_loss_limit,
        "strategy_loss": context.strategy_loss,
        "strategy_loss_limit": context.strategy_loss_limit,
        "duplicate_intent": context.duplicate_intent,
        "conflicting_intent": context.conflicting_intent,
    }


def _decision(
    context: RiskContext,
    *,
    approved: bool,
    reason_code: str,
    observed: Observed,
) -> RiskDecision:
    identity = json.dumps(
        {
            "idempotency_key": context.intent.idempotency_key,
            "approved": approved,
            "reason_code": reason_code,
            "observed": observed,
            "decided_at": context.decided_at.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return RiskDecision(
        decision_id=f"risk-{digest[:24]}",
        idempotency_key=context.intent.idempotency_key,
        approved=approved,
        reason_code=reason_code,
        observed_values=observed,
        decided_at=context.decided_at,
    )


def evaluate_entry_risk(context: RiskContext) -> RiskDecision:
    """Evaluate entry gates in a fixed fail-closed order."""

    observed = _base_observed(context)
    now = context.decided_at
    closeout_at = context.regular_close - context.closeout_buffer
    feed_age = now - context.feed_observed_at
    clock_age = now - context.broker_clock_observed_at

    reason: str | None = None
    if context.intent.symbol not in PRODUCTION_SYMBOLS:
        reason = "SYMBOL_NOT_ALLOWED"
    elif now < context.regular_open or now >= context.regular_close:
        reason = "OUTSIDE_REGULAR_HOURS"
    elif now >= closeout_at:
        reason = "CLOSEOUT_BUFFER_ACTIVE"
    elif feed_age < timedelta(0) or feed_age > context.max_feed_age:
        reason = "FEED_STALE"
    elif clock_age < timedelta(0) or clock_age > context.max_broker_clock_age:
        reason = "BROKER_CLOCK_STALE"
    elif context.reconciliation_status != "clean":
        reason = "RECONCILIATION_NOT_CLEAN"
    elif context.storage_circuit_open:
        reason = "STORAGE_CIRCUIT_OPEN"
    elif context.account_position_count >= 3:
        reason = "ACCOUNT_POSITION_LIMIT"
    elif context.strategy_entry_count >= 3:
        reason = "STRATEGY_ENTRY_LIMIT"
    elif context.strategy_state not in ENABLED_PAPER_STATES:
        reason = "STRATEGY_NOT_ENABLED"
    elif context.intent.side != "buy":
        reason = "LONG_ONLY_ENTRY_REQUIRED"
    elif context.available_cash < 0:
        reason = "NEGATIVE_CASH"
    elif not context.sizing.approved or context.sizing.quantity < 1:
        reason = "NO_FEASIBLE_INTEGER_POSITION"
    elif context.intent.quantity > context.sizing.quantity:
        reason = "QUANTITY_EXCEEDS_CONSERVATIVE_SIZE"
    elif context.sizing.required_cash > context.available_cash:
        reason = "MARGIN_OR_LEVERAGE_REQUIRED"
    elif context.daily_loss >= context.daily_loss_limit:
        reason = "DAILY_LOSS_LIMIT_BREACHED"
    elif context.account_loss >= context.account_loss_limit:
        reason = "ACCOUNT_LOSS_LIMIT_BREACHED"
    elif context.strategy_loss >= context.strategy_loss_limit:
        reason = "STRATEGY_LOSS_LIMIT_BREACHED"
    elif context.duplicate_intent:
        reason = "DUPLICATE_INTENT"
    elif context.conflicting_intent:
        reason = "CONFLICTING_INTENT"

    return _decision(
        context,
        approved=reason is None,
        reason_code=reason or "ENTRY_RISK_APPROVED",
        observed=observed,
    )
