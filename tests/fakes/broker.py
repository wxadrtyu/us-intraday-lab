"""Deterministic paper broker with controllable fills and failures."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from us_intraday_lab.contracts.orders import OrderIntent
from us_intraday_lab.contracts.paper import BrokerAccount, BrokerClock, BrokerOrder, BrokerPosition


class SubmitBehavior(str, Enum):
    ACCEPT = "accept"
    REJECT = "reject"
    PARTIAL_FILL = "partial_fill"
    DELAYED_FILL = "delayed_fill"
    FILL = "fill"
    TIMEOUT_AFTER_ACCEPT = "timeout_after_accept"


class FakePaperBroker:
    def __init__(self, *, now: datetime) -> None:
        self._now = now
        self._clock_observed_at = now
        self._connected = True
        self._behaviors: list[SubmitBehavior] = []
        self._orders: dict[str, BrokerOrder] = {}
        self._intents: dict[str, OrderIntent] = {}
        self._positions: dict[str, BrokerPosition] = {}
        self.submitted_idempotency_keys: list[str] = []
        self.submit_attempted_idempotency_keys: list[str] = []

    def _require_connection(self) -> None:
        if not self._connected:
            raise ConnectionError("FAKE_BROKER_DISCONNECTED")

    def account(self) -> BrokerAccount:
        self._require_connection()
        return BrokerAccount(
            account_id="fake-paper-account",
            account_number="PA-FAKE",
            broker_sdk_version="fake-1.0",
            status="ACTIVE",
            cash=25_000,
            buying_power=25_000,
            equity=25_000,
            trading_blocked=False,
            account_blocked=False,
            trade_suspended_by_user=False,
            multiplier=1,
            observed_at=self._now,
        )

    def clock(self) -> BrokerClock:
        self._require_connection()
        return BrokerClock(
            observed_at=self._clock_observed_at,
            is_open=True,
            next_open=self._now + timedelta(days=1),
            next_close=self._now + timedelta(hours=6),
        )

    def open_orders(self) -> tuple[BrokerOrder, ...]:
        self._require_connection()
        open_statuses = {"submitted", "accepted", "partially_filled"}
        return tuple(item for item in self._orders.values() if item.status in open_statuses)

    def positions(self) -> tuple[BrokerPosition, ...]:
        self._require_connection()
        return tuple(self._positions[symbol] for symbol in sorted(self._positions))

    def queue_submit_behavior(self, behavior: SubmitBehavior) -> None:
        self._behaviors.append(behavior)

    def submit(self, intent: OrderIntent) -> BrokerOrder:
        self._require_connection()
        self.submit_attempted_idempotency_keys.append(intent.idempotency_key)
        retained = self._orders.get(intent.idempotency_key)
        if retained is not None:
            if self._intents[intent.idempotency_key] != intent:
                raise ValueError("IDEMPOTENCY_KEY_CONTENT_MISMATCH")
            return retained
        behavior = self._behaviors.pop(0) if self._behaviors else SubmitBehavior.ACCEPT
        status = {
            SubmitBehavior.ACCEPT: "accepted",
            SubmitBehavior.REJECT: "rejected",
            SubmitBehavior.PARTIAL_FILL: "partially_filled",
            SubmitBehavior.DELAYED_FILL: "submitted",
            SubmitBehavior.FILL: "filled",
            SubmitBehavior.TIMEOUT_AFTER_ACCEPT: "accepted",
        }[behavior]
        filled_quantity = {
            SubmitBehavior.PARTIAL_FILL: max(1, intent.quantity // 2),
            SubmitBehavior.FILL: intent.quantity,
        }.get(behavior, 0)
        order = BrokerOrder(
            broker_order_id=f"fake-order-{len(self._orders) + 1}",
            client_order_id=intent.idempotency_key,
            symbol=intent.symbol,
            side=intent.side,
            order_type=intent.order_type,
            status=status,
            quantity=intent.quantity,
            filled_quantity=filled_quantity,
            average_fill_price=100.0 if filled_quantity else None,
            submitted_at=self._now,
            updated_at=self._now,
            rejection_reason="FAKE_REJECTION" if behavior is SubmitBehavior.REJECT else None,
        )
        self._intents[intent.idempotency_key] = intent
        self._orders[intent.idempotency_key] = order
        self.submitted_idempotency_keys.append(intent.idempotency_key)
        if behavior is SubmitBehavior.TIMEOUT_AFTER_ACCEPT:
            raise TimeoutError("FAKE_TIMEOUT_AFTER_ACCEPT")
        if behavior is SubmitBehavior.FILL and intent.side == "sell":
            position = self._positions.get(intent.symbol)
            if position is not None:
                remaining = position.quantity - intent.quantity
                if remaining <= 0:
                    del self._positions[intent.symbol]
                else:
                    self._positions[intent.symbol] = position.model_copy(
                        update={
                            "quantity": remaining,
                            "market_value": remaining * position.average_entry_price,
                            "observed_at": self._now,
                        }
                    )
        elif behavior in {SubmitBehavior.FILL, SubmitBehavior.PARTIAL_FILL} and intent.side == "buy":
            position = self._positions.get(intent.symbol)
            quantity = filled_quantity + (0 if position is None else position.quantity)
            self._positions[intent.symbol] = BrokerPosition(
                asset_id=f"asset-{intent.symbol.lower()}",
                symbol=intent.symbol,
                quantity=quantity,
                average_entry_price=100.0,
                market_value=quantity * 100.0,
                observed_at=self._now,
            )
        return order

    def cancel(self, broker_order_id: str) -> BrokerOrder:
        self._require_connection()
        current = next(
            (item for item in self._orders.values() if item.broker_order_id == broker_order_id),
            None,
        )
        if current is None:
            raise KeyError(broker_order_id)
        cancelled = current.model_copy(update={"status": "cancelled", "updated_at": self._now})
        self._orders[current.client_order_id] = cancelled
        return cancelled

    def fill_delayed(self, client_order_id: str, *, price: float = 100.0) -> BrokerOrder:
        current = self._orders[client_order_id]
        filled = current.model_copy(
            update={
                "status": "filled",
                "filled_quantity": current.quantity,
                "average_fill_price": price,
                "updated_at": self._now,
            }
        )
        self._orders[client_order_id] = filled
        intent = self._intents[client_order_id]
        if intent.side == "buy":
            previous = self._positions.get(intent.symbol)
            quantity = intent.quantity + (0 if previous is None else previous.quantity)
            self._positions[intent.symbol] = BrokerPosition(
                asset_id=f"asset-{intent.symbol.lower()}",
                symbol=intent.symbol,
                quantity=quantity,
                average_entry_price=price,
                market_value=quantity * price,
                observed_at=self._now,
            )
        elif intent.symbol in self._positions:
            del self._positions[intent.symbol]
        return filled

    def force_position(self, *, symbol: str, quantity: int, price: float) -> None:
        self._positions[symbol] = BrokerPosition(
            asset_id=f"asset-{symbol.lower()}",
            symbol=symbol,
            quantity=quantity,
            average_entry_price=price,
            market_value=quantity * price,
            observed_at=self._now,
        )

    def set_stale_clock(self, age: timedelta) -> None:
        self._clock_observed_at = self._now - age

    def set_now(self, now: datetime) -> None:
        self._now = now
        self._clock_observed_at = now

    def disconnect(self) -> None:
        self._connected = False

    def reconnect(self) -> None:
        self._connected = True
