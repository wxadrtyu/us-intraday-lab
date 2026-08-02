"""Minimal paper-only broker interface exposed to business logic."""

from __future__ import annotations

from typing import Protocol

from us_intraday_lab.contracts.orders import OrderIntent
from us_intraday_lab.contracts.paper import BrokerAccount, BrokerClock, BrokerOrder, BrokerPosition


class PaperBroker(Protocol):
    def account(self) -> BrokerAccount: ...

    def clock(self) -> BrokerClock: ...

    def open_orders(self) -> tuple[BrokerOrder, ...]: ...

    def positions(self) -> tuple[BrokerPosition, ...]: ...

    def submit(self, intent: OrderIntent) -> BrokerOrder: ...

    def cancel(self, broker_order_id: str) -> BrokerOrder: ...
