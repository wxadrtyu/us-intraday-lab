"""Automated, restart-safe paper-session coordination."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, Protocol, cast

import pandas as pd

from us_intraday_lab.backtest.clock import BacktestClock
from us_intraday_lab.contracts.market import MarketBarClosed
from us_intraday_lab.contracts.orders import OrderIntent
from us_intraday_lab.contracts.paper import (
    BrokerOrder,
    PaperCheckpoint,
    PositionSnapshot,
    ReconciliationResult,
    RiskDecision,
    StrategySessionState,
)
from us_intraday_lab.paper.broker import PaperBroker
from us_intraday_lab.paper.closeout import CloseoutResult, closeout_session
from us_intraday_lab.paper.market_data import MarketDataPipeline
from us_intraday_lab.paper.reconciliation import run_startup_reconciliation
from us_intraday_lab.paper.recovery import (
    build_order_idempotency_key,
    recover_session,
    replay_evidence,
)
from us_intraday_lab.paper.risk import RiskContext, evaluate_entry_risk
from us_intraday_lab.paper.sizing import SizingRequest, size_long_position
from us_intraday_lab.paper.store import PaperStore
from us_intraday_lab.strategy.features import compute_feature_frame
from us_intraday_lab.strategy.operators import (
    AllOperator,
    AnyOperator,
    ComparisonOperator,
    CompiledStrategy,
    RuleOperator,
)


class SessionStrategy(Protocol):
    strategy_id: str
    symbol: str
    lifecycle_state: str
    stop_loss_bps: int
    risk_fraction: float
    max_position_fraction: float
    daily_loss_limit: float
    account_loss_limit: float
    strategy_loss_limit: float
    order_type: Literal["market", "limit"]

    def should_enter(self, bar: MarketBarClosed) -> bool: ...


def _rule_matches(rule: RuleOperator, features: dict[str, object]) -> bool:
    if isinstance(rule, ComparisonOperator):
        value = rule.indicator_fn(features)  # type: ignore[arg-type]
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            return False
        return rule.comparison_fn(float(value), rule.threshold)
    if isinstance(rule, AllOperator):
        return all(_rule_matches(child, features) for child in rule.children)
    if isinstance(rule, AnyOperator):
        return any(_rule_matches(child, features) for child in rule.children)
    raise TypeError("unknown compiled rule")


class CompiledSessionStrategy:
    """Evaluate one compiled DSL strategy/symbol from completed paper bars."""

    risk_fraction = 0.005
    max_position_fraction = 0.25
    daily_loss_limit = 500.0
    account_loss_limit = 1_000.0
    strategy_loss_limit = 250.0

    def __init__(
        self,
        *,
        compiled: CompiledStrategy,
        symbol: str,
        lifecycle_state: str,
        history: tuple[MarketBarClosed, ...] = (),
    ) -> None:
        if symbol not in compiled.symbols:
            raise ValueError("strategy symbol is not compiled")
        self._compiled = compiled
        self.strategy_id = compiled.strategy_id
        self.symbol = symbol
        self.lifecycle_state = lifecycle_state
        self.stop_loss_bps = compiled.risk.stop_loss_bps
        self.order_type = compiled.order_type
        self._history = [bar for bar in history if bar.symbol == symbol and bar.timeframe == "15min"]

    def should_enter(self, bar: MarketBarClosed) -> bool:
        if bar.symbol != self.symbol or bar.timeframe != "15min":
            return False
        if not any(item.provider_event_id == bar.provider_event_id for item in self._history):
            self._history.append(bar)
        frame = pd.DataFrame(
            [
                {
                    "symbol": item.symbol,
                    "session_date": item.bar_start.date(),
                    "bar_start": item.bar_start,
                    "available_at": item.available_at,
                    "open": item.open,
                    "high": item.high,
                    "low": item.low,
                    "close": item.close,
                    "volume": item.volume,
                }
                for item in self._history
            ]
        )
        features = compute_feature_frame(frame)
        if features.empty:
            return False
        return _rule_matches(
            self._compiled.entry,
            cast(dict[str, object], features.iloc[-1].to_dict()),
        )


@dataclass(frozen=True, slots=True)
class SessionRunResult:
    entries_enabled: bool
    submitted_entry_count: int
    reason_codes: tuple[str, ...]


def _digest(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


class PaperSessionService:
    """Coordinate durable market, risk, broker, and position transitions."""

    def __init__(
        self,
        *,
        store: PaperStore,
        broker: PaperBroker,
        market_data: MarketDataPipeline,
        strategies: Sequence[SessionStrategy],
        session_date: date,
        closeout_buffer_minutes: int,
    ) -> None:
        session = store.get_session(market_data.paper_session_id)
        if session is None or session.session_date != session_date:
            raise ValueError("PAPER_SESSION_DATE_MISMATCH")
        identities = {(item.strategy_id, item.symbol) for item in strategies}
        if len(identities) != len(strategies):
            raise ValueError("SESSION_STRATEGY_SYMBOLS_MUST_BE_UNIQUE")
        self.store = store
        self.broker = broker
        self.market_data = market_data
        self.strategies = tuple(strategies)
        self.session_date = session_date
        self.paper_session_id = market_data.paper_session_id
        self.clock = BacktestClock(
            session_date=session_date,
            closeout_buffer_minutes=closeout_buffer_minutes,
        )
        self._reconciliation: ReconciliationResult | None = None
        self._pending_aggregates = [
            event
            for event in store.list_market_events(self.paper_session_id)
            if event.timeframe == "15min"
        ]

    def start(self, *, completed_at: datetime) -> ReconciliationResult:
        recover_session(store=self.store, paper_session_id=self.paper_session_id)
        self._reconciliation = run_startup_reconciliation(
            store=self.store,
            broker=self.broker,
            paper_session_id=self.paper_session_id,
            completed_at=completed_at,
        )
        return self._reconciliation

    def process_bars(
        self,
        bars: tuple[MarketBarClosed, ...],
        *,
        observed_at: datetime,
    ) -> SessionRunResult:
        if self._reconciliation is None or not self._reconciliation.entries_enabled:
            return SessionRunResult(False, 0, ("RECONCILIATION_NOT_CLEAN",))
        if self.store.entry_writes_disabled:
            return SessionRunResult(False, 0, ("STORAGE_CIRCUIT_OPEN",))
        aggregates: list[MarketBarClosed] = []
        try:
            for bar in bars:
                aggregates.extend(self.market_data.ingest(bar))
        except (
            ConnectionError,
            TimeoutError,
            OSError,
            RuntimeError,
            ValueError,
            sqlite3.Error,
        ):
            return SessionRunResult(False, 0, ("MARKET_DATA_INGEST_FAILURE",))
        health = self.market_data.health(observed_at=observed_at)
        if not health.entries_enabled:
            return SessionRunResult(False, 0, health.reason_codes)

        for aggregate in aggregates:
            if not any(
                item.provider_event_id == aggregate.provider_event_id
                for item in self._pending_aggregates
            ):
                self._pending_aggregates.append(aggregate)
        eligible_aggregates = tuple(
            item
            for item in self._pending_aggregates
            if item.available_at + timedelta(minutes=1) <= observed_at
        )

        submitted = 0
        rejected_reasons: set[str] = set()
        for bar in eligible_aggregates:
            for strategy in self.strategies:
                if strategy.symbol != bar.symbol or not strategy.should_enter(bar):
                    continue
                try:
                    if self._signal_already_processed(strategy, bar):
                        continue
                    if self._submit_entry(strategy, bar, observed_at=observed_at):
                        submitted += 1
                except (ConnectionError, TimeoutError):
                    rejected_reasons.add("BROKER_SUBMISSION_UNCERTAIN")
                except (OSError, RuntimeError, ValueError, sqlite3.Error):
                    rejected_reasons.add("PAPER_ENTRY_FAILURE")
            self._pending_aggregates.remove(bar)
        return SessionRunResult(
            entries_enabled=not rejected_reasons,
            submitted_entry_count=submitted,
            reason_codes=tuple(sorted(rejected_reasons)),
        )

    def _signal_already_processed(
        self, strategy: SessionStrategy, bar: MarketBarClosed
    ) -> bool:
        return any(
            intent.strategy_id == strategy.strategy_id
            and intent.symbol == strategy.symbol
            and intent.side == "buy"
            and intent.signal_time == bar.available_at
            for intent in self.store.list_order_intents(self.paper_session_id)
        )

    def _submit_entry(
        self,
        strategy: SessionStrategy,
        bar: MarketBarClosed,
        *,
        observed_at: datetime,
    ) -> bool:
        if self._reconciliation is None:
            raise RuntimeError("PAPER_SESSION_NOT_STARTED")
        state = self.store.get_strategy_session_state(
            self.paper_session_id, strategy.strategy_id
        )
        entry_count = 0 if state is None else state.entry_count
        account = self.broker.account()
        broker_clock = self.broker.clock()
        sizing = size_long_position(
            SizingRequest(
                available_cash=account.cash,
                account_equity=account.equity,
                reference_price=bar.close,
                stop_distance=bar.close * strategy.stop_loss_bps / 10_000,
                strategy_risk_fraction=strategy.risk_fraction,
                max_position_fraction=strategy.max_position_fraction,
            )
        )
        if not sizing.approved:
            return False
        eligible_at = bar.available_at + timedelta(minutes=1)
        if observed_at < eligible_at:
            return False
        order_type = cast(
            Literal["market", "limit"], getattr(strategy, "order_type", "market")
        )
        intent = OrderIntent(
            schema_version="1.0.0",
            run_id=self.paper_session_id,
            strategy_id=strategy.strategy_id,
            symbol=strategy.symbol,
            session=self.session_date,
            side="buy",
            order_type=order_type if order_type in {"market", "limit"} else "market",
            quantity=sizing.quantity,
            limit_price=bar.close if order_type == "limit" else None,
            signal_time=bar.available_at,
            eligible_time=eligible_at,
            reason_code="entry_signal",
            idempotency_key=build_order_idempotency_key(
                paper_session_id=self.paper_session_id,
                strategy_id=strategy.strategy_id,
                symbol=strategy.symbol,
                signal_available_at=bar.available_at,
                action="entry",
                entry_sequence=min(entry_count + 1, 3),
            ),
        )
        open_orders = self.broker.open_orders()
        decision = evaluate_entry_risk(
            RiskContext(
                intent=intent,
                decided_at=observed_at,
                regular_open=self.clock.session_open,
                regular_close=self.clock.session_close,
                closeout_buffer=timedelta(
                    minutes=int(
                        (self.clock.session_close - self.clock.closeout_time).total_seconds()
                        // 60
                    )
                ),
                feed_observed_at=bar.available_at,
                broker_clock_observed_at=broker_clock.observed_at,
                max_feed_age=self.market_data.stale_after,
                max_broker_clock_age=timedelta(seconds=5),
                reconciliation_status=self._reconciliation.status,
                storage_circuit_open=self.store.entry_writes_disabled,
                account_position_count=len(self.broker.positions()),
                strategy_entry_count=entry_count,
                strategy_state=strategy.lifecycle_state,
                available_cash=account.cash,
                account_multiplier=account.multiplier,
                sizing=sizing,
                daily_loss=0.0,
                daily_loss_limit=strategy.daily_loss_limit,
                account_loss=0.0,
                account_loss_limit=strategy.account_loss_limit,
                strategy_loss=0.0,
                strategy_loss_limit=strategy.strategy_loss_limit,
                duplicate_intent=False,
                conflicting_intent=any(
                    item.symbol == strategy.symbol and item.side == "buy"
                    for item in open_orders
                ),
            )
        )
        if not decision.approved:
            return False
        broker_order = self.broker.submit(intent)
        self._record_submission(intent, decision, broker_order, observed_at=observed_at)
        positions = self.broker.positions()
        self.store.append_position_snapshot(
            PositionSnapshot(
                snapshot_id="paper-position-"
                + _digest(
                    {
                        "order": broker_order.client_order_id,
                        "positions": [(item.symbol, item.quantity) for item in positions],
                    }
                )[:24],
                paper_session_id=self.paper_session_id,
                positions=positions,
                observed_at=observed_at,
            )
        )
        position_quantity = sum(
            item.quantity for item in positions if item.symbol == strategy.symbol
        )
        self.store.upsert_strategy_session_state(
            StrategySessionState(
                paper_session_id=self.paper_session_id,
                strategy_id=strategy.strategy_id,
                entry_count=entry_count + 1,
                position_quantity=position_quantity,
                last_signal_at=bar.available_at,
                updated_at=observed_at,
            )
        )
        return True

    def _record_submission(
        self,
        intent: OrderIntent,
        decision: RiskDecision,
        broker_order: BrokerOrder,
        *,
        observed_at: datetime,
    ) -> None:
        state = replay_evidence(
            paper_session_id=self.paper_session_id,
            market_events=self.store.list_market_events(self.paper_session_id),
            order_events=self.store.list_order_events(self.paper_session_id) + (broker_order,),
            position_snapshots=self.store.list_position_snapshots(self.paper_session_id),
        )
        latest = self.store.latest_checkpoint(self.paper_session_id)
        sequence = 1 if latest is None else latest.event_sequence + 1
        checkpoint = PaperCheckpoint(
            checkpoint_id=f"paper-checkpoint-{sequence}-{state.content_sha256[:16]}",
            paper_session_id=self.paper_session_id,
            event_sequence=sequence,
            state_sha256=state.content_sha256,
            created_at=max(observed_at, broker_order.updated_at),
        )
        self.store.record_order_bundle(
            intent=intent,
            risk_decision=decision,
            broker_order=broker_order,
            checkpoint=checkpoint,
        )

    def process_order_update(
        self, order: BrokerOrder, *, observed_at: datetime
    ) -> bool:
        latest = tuple(
            item
            for item in self.store.list_order_events(self.paper_session_id)
            if item.client_order_id == order.client_order_id
        )
        if latest and latest[-1] == order:
            return False
        intent = self.store.get_order_intent(order.client_order_id)
        decision = self.store.get_risk_decision(order.client_order_id)
        if intent is None or decision is None:
            raise ValueError("UNKNOWN_ORDER_UPDATE")
        self._record_submission(intent, decision, order, observed_at=observed_at)
        positions = self.broker.positions()
        self.store.append_position_snapshot(
            PositionSnapshot(
                snapshot_id="paper-position-update-"
                + _digest(
                    {
                        "order": order.model_dump(mode="json"),
                        "positions": [(item.symbol, item.quantity) for item in positions],
                    }
                )[:24],
                paper_session_id=self.paper_session_id,
                positions=positions,
                observed_at=observed_at,
            )
        )
        current = self.store.get_strategy_session_state(
            self.paper_session_id, intent.strategy_id
        )
        if current is not None:
            self.store.upsert_strategy_session_state(
                current.model_copy(
                    update={
                        "position_quantity": sum(
                            item.quantity for item in positions if item.symbol == intent.symbol
                        ),
                        "updated_at": observed_at,
                    }
                )
            )
        return True

    def closeout(self, *, closeout_at: datetime) -> CloseoutResult:
        return closeout_session(
            broker=self.broker,
            store=self.store,
            paper_session_id=self.paper_session_id,
            strategy_ids_by_symbol={item.symbol: item.strategy_id for item in self.strategies},
            closeout_at=closeout_at,
            max_cancel_polls=3,
            max_exit_attempts=3,
            max_flat_polls=3,
        )
