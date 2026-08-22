"""Paper-only Alpaca execution controller for the frozen v449 candidate."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import time as time_module
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import pandas as pd

from us_intraday_lab.contracts.orders import OrderIntent
from us_intraday_lab.contracts.paper import BrokerOrder
from us_intraday_lab.paper.broker import PaperBroker
from us_intraday_lab.research_shadow_alpaca import NEW_YORK
from us_intraday_lab.v45_research_shadow import (
    EXIT_BAR,
    HORIZONS,
    _bucket,
    _prior20,
    _raw_return,
    _signal,
)
from us_intraday_lab.v449_research_shadow import (
    ANCHOR_WEIGHT,
    COMPONENT_DECISION,
    COMPONENT_EXIT,
    COMPONENT_WEIGHT,
    _component_raw_return,
    _component_signal,
)

CANDIDATE_ID = "lev-v449-03e9e3f9c4b21390"
STRATEGY_ASSETS = ("TQQQ", "SOXL")
TARGET_VOLATILITY = 0.35
CAPITAL_BUFFER = 0.99
TERMINAL_STATUSES = {"filled", "cancelled", "expired", "rejected"}


@dataclass(frozen=True, slots=True)
class SleeveSignal:
    sleeve: Literal["anchor", "component"]
    symbol: Literal["TQQQ", "SOXL"]
    decision_bar: int
    exit_bar: int
    weight: float
    exposure: float


class V449PaperLedger:
    """Append-only local evidence ledger; rows cannot be updated or deleted."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._connection = sqlite3.connect(path)
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_key TEXT NOT NULL UNIQUE,
                session_date TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                payload_sha256 TEXT NOT NULL,
                occurred_at TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS events_no_update
            BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT, 'EVENTS_APPEND_ONLY'); END;
            CREATE TRIGGER IF NOT EXISTS events_no_delete
            BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT, 'EVENTS_APPEND_ONLY'); END;
            """
        )

    def append(
        self,
        *,
        event_key: str,
        session_date: date,
        event_type: str,
        payload: dict[str, Any],
        occurred_at: datetime | None = None,
    ) -> bool:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        timestamp = (occurred_at or datetime.now(UTC)).astimezone(UTC).isoformat()
        try:
            with self._connection:
                self._connection.execute(
                    "INSERT INTO events(event_key,session_date,event_type,payload_json,"
                    "payload_sha256,occurred_at) VALUES(?,?,?,?,?,?)",
                    (event_key, session_date.isoformat(), event_type, encoded, digest, timestamp),
                )
        except sqlite3.IntegrityError as error:
            if "UNIQUE constraint failed" not in str(error):
                raise
            return False
        return True

    def payload(self, event_key: str) -> dict[str, Any] | None:
        row = self._connection.execute(
            "SELECT payload_json FROM events WHERE event_key=?", (event_key,)
        ).fetchone()
        return None if row is None else json.loads(str(row[0]))

    def events(self, session_date: date, event_type: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT event_key,event_type,payload_json,occurred_at FROM events WHERE session_date=?"
        parameters: list[str] = [session_date.isoformat()]
        if event_type is not None:
            query += " AND event_type=?"
            parameters.append(event_type)
        query += " ORDER BY sequence"
        return [
            {
                "event_key": row[0],
                "event_type": row[1],
                "payload": json.loads(row[2]),
                "occurred_at": row[3],
            }
            for row in self._connection.execute(query, parameters)
        ]


def _volatility_exposure(raw_history: list[float]) -> float:
    realized = float(np.std(raw_history, ddof=1) * np.sqrt(252.0))
    return min(1.0, TARGET_VOLATILITY / realized) if realized > 1e-8 else 1.0


def signals_at(bars: pd.DataFrame, *, session_date: date, decision_bar: int) -> tuple[SleeveSignal, ...]:
    """Evaluate the frozen factor logic only with bars available at decision time."""

    buckets, sessions, _ = _bucket(bars)
    if session_date not in sessions:
        raise ValueError("V449_TARGET_SESSION_ABSENT")
    target_index = sessions.index(session_date)
    if target_index < 35:
        raise ValueError("V449_REQUIRES_35_PRIOR_SESSIONS")
    prior = _prior20(buckets, sessions)
    signals: list[SleeveSignal] = []
    if decision_bar == COMPONENT_DECISION:
        component_symbol = _component_signal(buckets, session_date)
        if component_symbol is not None:
            raw = [
                _component_raw_return(buckets, sessions[index], cost=0.0009, delay=0)[0]
                for index in range(target_index - 15, target_index)
            ]
            signals.append(
                SleeveSignal(
                    sleeve="component",
                    symbol=cast(Literal["TQQQ", "SOXL"], component_symbol),
                    decision_bar=decision_bar,
                    exit_bar=COMPONENT_EXIT,
                    weight=COMPONENT_WEIGHT,
                    exposure=_volatility_exposure(raw),
                )
            )
    if decision_bar in HORIZONS:
        anchor_symbol, selected_at = _signal(buckets, session_date, prior.iloc[target_index])
        if anchor_symbol is not None and selected_at == decision_bar:
            raw = [
                _raw_return(
                    buckets, sessions[index], prior.iloc[index], cost=0.0009, delay=0
                )[0]
                for index in range(target_index - 15, target_index)
            ]
            signals.append(
                SleeveSignal(
                    sleeve="anchor",
                    symbol=cast(Literal["TQQQ", "SOXL"], anchor_symbol),
                    decision_bar=decision_bar,
                    exit_bar=EXIT_BAR,
                    weight=ANCHOR_WEIGHT,
                    exposure=_volatility_exposure(raw),
                )
            )
    return tuple(signals)


class V449PaperController:
    """Idempotent cash-only controller used by one strategy allocation in a paper pool."""

    def __init__(
        self,
        *,
        broker: PaperBroker,
        ledger: V449PaperLedger,
        candidate_id: str = CANDIDATE_ID,
        strategy_code: str = "v449",
        account_fraction: float = 1.0,
        managed_strategy_codes: tuple[str, ...] | None = None,
    ) -> None:
        if not 0.0 < account_fraction <= 1.0:
            raise ValueError("PAPER_ACCOUNT_FRACTION_OUT_OF_RANGE")
        if not strategy_code or not strategy_code.isalnum():
            raise ValueError("PAPER_STRATEGY_CODE_INVALID")
        self.broker = broker
        self.ledger = ledger
        self.candidate_id = candidate_id
        self.strategy_code = strategy_code
        self.account_fraction = account_fraction
        self.managed_strategy_codes = managed_strategy_codes or (strategy_code,)

    def client_order_id(self, session_date: date, sleeve: str, action: str) -> str:
        return f"{self.strategy_code}-{session_date:%Y%m%d}-{sleeve[0]}-{action}"

    def startup_check(self, session_date: date) -> None:
        account = self.broker.account()
        if account.multiplier > 1:
            self.ledger.append(
                event_key=f"{session_date}:account-cash-only",
                session_date=session_date,
                event_type="ACCOUNT_BOUNDARY",
                payload={"cash_only": True, "broker_multiplier_ignored": account.multiplier},
            )
        session_prefixes = tuple(
            f"{strategy_code}-{session_date:%Y%m%d}-"
            for strategy_code in self.managed_strategy_codes
        )
        foreign_orders = [
            item
            for item in self.broker.open_orders()
            if not item.client_order_id.startswith(session_prefixes)
        ]
        foreign_positions = [
            item for item in self.broker.positions() if item.symbol not in STRATEGY_ASSETS
        ]
        if foreign_orders or foreign_positions:
            self.ledger.append(
                event_key=f"{session_date}:startup-blocked",
                session_date=session_date,
                event_type="INCIDENT",
                payload={
                    "reason": "DEDICATED_ACCOUNT_CONTAMINATED",
                    "foreign_order_count": len(foreign_orders),
                    "foreign_position_symbols": [item.symbol for item in foreign_positions],
                },
            )
            raise RuntimeError("DEDICATED_ACCOUNT_CONTAMINATED")
        expected: dict[str, int] = {}
        for strategy_code in self.managed_strategy_codes:
            for sleeve in ("component", "anchor"):
                prefix = f"{strategy_code}-{session_date:%Y%m%d}-{sleeve[0]}"
                entry = self.broker.order_by_client_id(f"{prefix}-entry")
                exit_order = self.broker.order_by_client_id(f"{prefix}-exit")
                if entry is not None:
                    expected[entry.symbol] = expected.get(entry.symbol, 0) + entry.filled_quantity
                if exit_order is not None:
                    expected[exit_order.symbol] = (
                        expected.get(exit_order.symbol, 0) - exit_order.filled_quantity
                    )
        expected = {symbol: quantity for symbol, quantity in expected.items() if quantity > 0}
        observed = {
            item.symbol: item.quantity
            for item in self.broker.positions()
            if item.symbol in STRATEGY_ASSETS
        }
        if observed != expected:
            self.ledger.append(
                event_key=f"{session_date}:position-reconciliation-blocked",
                session_date=session_date,
                event_type="INCIDENT",
                payload={"reason": "V449_POSITION_MISMATCH", "expected": expected, "observed": observed},
            )
            raise RuntimeError("V449_POSITION_MISMATCH")

    def _submit_once(self, intent: OrderIntent) -> BrokerOrder:
        prepared_key = f"prepared:{intent.idempotency_key}"
        self.ledger.append(
            event_key=prepared_key,
            session_date=intent.session,
            event_type="ORDER_PREPARED",
            payload=intent.model_dump(mode="json"),
            occurred_at=intent.signal_time,
        )
        existing = self.broker.order_by_client_id(intent.idempotency_key)
        order = existing if existing is not None else self.broker.submit(intent)
        self.ledger.append(
            event_key=f"broker:{intent.idempotency_key}:{order.status}:{order.filled_quantity}",
            session_date=intent.session,
            event_type="BROKER_ORDER",
            payload=order.model_dump(mode="json"),
            occurred_at=order.updated_at,
        )
        return order

    def enter(
        self,
        *,
        session_date: date,
        signal: SleeveSignal,
        reference_price: float,
        now: datetime,
    ) -> BrokerOrder | None:
        if reference_price <= 0 or not math.isfinite(reference_price):
            raise ValueError("V449_REFERENCE_PRICE_INVALID")
        client_id = self.client_order_id(session_date, signal.sleeve, "entry")
        if self.broker.order_by_client_id(client_id) is not None:
            return None
        account = self.broker.account()
        target = (
            account.equity
            * self.account_fraction
            * signal.weight
            * signal.exposure
            * CAPITAL_BUFFER
        )
        target = min(target, account.cash * CAPITAL_BUFFER)
        quantity = int(target // reference_price)
        if quantity < 1:
            self.ledger.append(
                event_key=f"{session_date}:{signal.sleeve}:size-zero",
                session_date=session_date,
                event_type="SKIP",
                payload={"reason": "INSUFFICIENT_CASH", "target_notional": target},
            )
            return None
        intent = OrderIntent(
            schema_version="1.0.0",
            run_id=f"{self.strategy_code}-{session_date:%Y%m%d}",
            strategy_id=self.candidate_id,
            symbol=signal.symbol,
            session=session_date,
            side="buy",
            order_type="market",
            quantity=quantity,
            signal_time=now.astimezone(UTC),
            eligible_time=now.astimezone(UTC),
            reason_code="entry_signal",
            idempotency_key=client_id,
        )
        return self._submit_once(intent)

    def exit_sleeve(self, *, session_date: date, sleeve: str, now: datetime) -> BrokerOrder | None:
        entry_id = self.client_order_id(session_date, sleeve, "entry")
        entry = self.broker.order_by_client_id(entry_id)
        if entry is None:
            return None
        if entry.status not in TERMINAL_STATUSES:
            entry = self.broker.cancel(entry.broker_order_id)
        quantity = entry.filled_quantity
        if quantity < 1:
            return None
        exit_id = self.client_order_id(session_date, sleeve, "exit")
        if self.broker.order_by_client_id(exit_id) is not None:
            return None
        intent = OrderIntent(
            schema_version="1.0.0",
            run_id=f"{self.strategy_code}-{session_date:%Y%m%d}",
            strategy_id=self.candidate_id,
            symbol=entry.symbol,
            session=session_date,
            side="sell",
            order_type="market",
            quantity=quantity,
            signal_time=now.astimezone(UTC),
            eligible_time=now.astimezone(UTC),
            reason_code="session_close",
            idempotency_key=exit_id,
        )
        return self._submit_once(intent)

    def emergency_flatten(self, *, session_date: date, now: datetime) -> tuple[BrokerOrder, ...]:
        for order in self.broker.open_orders():
            if order.client_order_id.startswith(
                tuple(f"{code}-{session_date:%Y%m%d}-" for code in self.managed_strategy_codes)
            ):
                self.broker.cancel(order.broker_order_id)
        results = []
        for position in self.broker.positions():
            if position.symbol not in STRATEGY_ASSETS:
                raise RuntimeError("EMERGENCY_CLOSE_FOREIGN_POSITION_BLOCKED")
            client_id = f"{self.strategy_code}-{session_date:%Y%m%d}-z-flat-{position.symbol.lower()}"
            existing = self.broker.order_by_client_id(client_id)
            if existing is not None:
                results.append(existing)
                continue
            intent = OrderIntent(
                schema_version="1.0.0",
                run_id=f"{self.strategy_code}-{session_date:%Y%m%d}",
                strategy_id=self.candidate_id,
                symbol=position.symbol,
                session=session_date,
                side="sell",
                order_type="market",
                quantity=position.quantity,
                signal_time=now.astimezone(UTC),
                eligible_time=now.astimezone(UTC),
                reason_code="session_close",
                idempotency_key=client_id,
            )
            results.append(self._submit_once(intent))
        self.ledger.append(
            event_key=f"{session_date}:emergency-flat-invoked",
            session_date=session_date,
            event_type="CLOSEOUT",
            payload={"orders": len(results)},
            occurred_at=now,
        )
        return tuple(results)


def ny_bar_time(session_date: date, bar: int) -> datetime:
    return datetime.combine(session_date, time(9, 30), NEW_YORK) + timedelta(minutes=bar * 5)


def wait_until(target: datetime) -> None:
    while True:
        remaining = (target.astimezone(UTC) - datetime.now(UTC)).total_seconds()
        if remaining <= 0:
            return
        time_module.sleep(min(remaining, 30.0))
