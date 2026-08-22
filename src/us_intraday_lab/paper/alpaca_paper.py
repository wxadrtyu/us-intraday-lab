"""Alpaca adapter whose construction and operations are permanently paper-only."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from importlib.metadata import version
from typing import Any, Literal, Protocol, cast

from pydantic import BaseModel, ConfigDict

from us_intraday_lab.contracts.orders import OrderIntent, OrderStatus
from us_intraday_lab.contracts.paper import BrokerAccount, BrokerClock, BrokerOrder, BrokerPosition

ALPACA_PAPER_ENDPOINT: Literal["https://paper-api.alpaca.markets"] = (
    "https://paper-api.alpaca.markets"
)
PAPER_KEY_VARIABLE = "ALPACA_PAPER_API_KEY"
PAPER_SECRET_VARIABLE = "ALPACA_PAPER_SECRET_KEY"


class PaperBoundaryError(RuntimeError):
    """Raised whenever the adapter cannot prove its paper-only boundary."""


class AlpacaPaperConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    endpoint: Literal["https://paper-api.alpaca.markets"] = ALPACA_PAPER_ENDPOINT
    environment: Literal["paper"] = "paper"


class _TradingClient(Protocol):
    def get_account(self) -> Any: ...

    def get_clock(self) -> Any: ...

    def get_orders(self, *, filter: object) -> Any: ...

    def get_all_positions(self) -> Any: ...

    def submit_order(self, *, order_data: object) -> Any: ...

    def cancel_order_by_id(self, order_id: str) -> Any: ...

    def get_order_by_id(self, order_id: str) -> Any: ...

    def get_order_by_client_id(self, client_id: str) -> Any: ...


ClientFactory = Callable[..., _TradingClient]
_BOUNDARY_TOKEN = object()


def _default_client_factory(*, api_key: str, secret_key: str, paper: bool) -> _TradingClient:
    from alpaca.trading.client import TradingClient

    if paper is not True:
        raise PaperBoundaryError("SDK_PAPER_MODE_REQUIRED")
    return cast(
        _TradingClient,
        TradingClient(api_key=api_key, secret_key=secret_key, paper=True),
    )


def _value(value: object) -> str:
    raw = getattr(value, "value", value)
    return str(raw)


def _money(value: object, *, name: str) -> float:
    try:
        result = float(Decimal(str(value)))
    except (InvalidOperation, ValueError) as error:
        raise PaperBoundaryError(f"ACCOUNT_{name.upper()}_INVALID") from error
    if result < 0:
        raise PaperBoundaryError(f"ACCOUNT_{name.upper()}_INVALID")
    return result


def _timestamp(value: object, *, name: str) -> datetime:
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise PaperBoundaryError(f"BROKER_{name.upper()}_INVALID")
    return value.astimezone(UTC)


class AlpacaPaperBroker:
    """Translate the small internal protocol to one immutable Alpaca paper client."""

    def __init__(
        self,
        *,
        _token: object,
        _client: _TradingClient,
        _sdk_version: str,
    ) -> None:
        if _token is not _BOUNDARY_TOKEN:
            raise PaperBoundaryError("USE_PAPER_ENVIRONMENT_FACTORY")
        self._config = AlpacaPaperConfig()
        self._sdk_version = _sdk_version
        self._client = _client
        sdk_endpoint = getattr(self._client, "_base_url", None)
        if _value(sdk_endpoint).rstrip("/") != self._config.endpoint:
            raise PaperBoundaryError("PAPER_ENDPOINT_MISMATCH")
        self._validate_account(self._map_account(self._client.get_account()))

    @classmethod
    def from_environment(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        client_factory: ClientFactory = _default_client_factory,
    ) -> AlpacaPaperBroker:
        values = os.environ if environ is None else environ
        api_key = values.get(PAPER_KEY_VARIABLE, "")
        secret_key = values.get(PAPER_SECRET_VARIABLE, "")
        missing = [
            name
            for name, value in (
                (PAPER_KEY_VARIABLE, api_key),
                (PAPER_SECRET_VARIABLE, secret_key),
            )
            if not value
        ]
        if missing:
            raise PaperBoundaryError("PAPER_CREDENTIAL_MISSING:" + ",".join(missing))
        client = client_factory(api_key=api_key, secret_key=secret_key, paper=True)
        return cls(
            _token=_BOUNDARY_TOKEN,
            _client=client,
            _sdk_version=version("alpaca-py"),
        )

    @property
    def endpoint(self) -> str:
        return self._config.endpoint

    def _map_account(self, raw: Any) -> BrokerAccount:
        try:
            multiplier = int(Decimal(str(raw.multiplier)))
            status = _value(raw.status).upper()
            currency = _value(raw.currency).upper()
            if status not in {"ACTIVE", "PAPER_ONLY"}:
                raise PaperBoundaryError("ACCOUNT_NOT_ACTIVE")
            if currency != "USD":
                raise PaperBoundaryError("ACCOUNT_NOT_USD")
            return BrokerAccount(
                account_id=str(raw.id),
                account_number=str(raw.account_number),
                broker_sdk_version=self._sdk_version,
                status=cast(Any, status),
                currency=cast(Any, currency),
                cash=_money(raw.cash, name="cash"),
                buying_power=_money(raw.buying_power, name="buying_power"),
                equity=_money(raw.equity, name="equity"),
                trading_blocked=bool(raw.trading_blocked),
                account_blocked=bool(raw.account_blocked),
                trade_suspended_by_user=bool(raw.trade_suspended_by_user),
                multiplier=multiplier,
                observed_at=datetime.now(UTC),
            )
        except PaperBoundaryError:
            raise
        except (AttributeError, InvalidOperation, ValueError) as error:
            raise PaperBoundaryError("ACCOUNT_RESPONSE_INVALID") from error

    @staticmethod
    def _validate_account(account: BrokerAccount) -> None:
        if account.status not in {"ACTIVE", "PAPER_ONLY"}:
            raise PaperBoundaryError("ACCOUNT_NOT_ACTIVE")
        if account.currency != "USD":
            raise PaperBoundaryError("ACCOUNT_NOT_USD")
        if account.account_blocked:
            raise PaperBoundaryError("ACCOUNT_BLOCKED")
        if account.trade_suspended_by_user:
            raise PaperBoundaryError("ACCOUNT_TRADING_SUSPENDED")
        if account.trading_blocked:
            raise PaperBoundaryError("ACCOUNT_TRADING_BLOCKED")

    def account(self) -> BrokerAccount:
        account = self._map_account(self._client.get_account())
        self._validate_account(account)
        return account

    def clock(self) -> BrokerClock:
        raw = self._client.get_clock()
        return BrokerClock(
            observed_at=_timestamp(getattr(raw, "timestamp", None), name="clock_timestamp"),
            is_open=bool(getattr(raw, "is_open", False)),
            next_open=_timestamp(getattr(raw, "next_open", None), name="next_open"),
            next_close=_timestamp(getattr(raw, "next_close", None), name="next_close"),
        )

    def open_orders(self) -> tuple[BrokerOrder, ...]:
        from alpaca.trading.enums import QueryOrderStatus
        from alpaca.trading.requests import GetOrdersRequest

        request = GetOrdersRequest(status=QueryOrderStatus.OPEN)
        return tuple(self._map_order(item) for item in self._client.get_orders(filter=request))

    def positions(self) -> tuple[BrokerPosition, ...]:
        observed_at = datetime.now(UTC)
        return tuple(
            self._map_position(item, observed_at=observed_at)
            for item in self._client.get_all_positions()
        )

    def submit(self, intent: OrderIntent) -> BrokerOrder:
        from alpaca.trading.enums import OrderSide as AlpacaOrderSide
        from alpaca.trading.enums import TimeInForce
        from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest

        common = {
            "symbol": intent.symbol,
            "qty": intent.quantity,
            "side": AlpacaOrderSide.BUY if intent.side == "buy" else AlpacaOrderSide.SELL,
            "time_in_force": TimeInForce.DAY,
            "client_order_id": intent.idempotency_key,
        }
        request: object
        if intent.order_type == "market":
            request = MarketOrderRequest(**common)
        else:
            request = LimitOrderRequest(**common, limit_price=intent.limit_price)
        return self._map_order(self._client.submit_order(order_data=request))

    def cancel(self, broker_order_id: str) -> BrokerOrder:
        if type(broker_order_id) is not str or not broker_order_id:
            raise ValueError("broker_order_id must be a non-empty string")
        self._client.cancel_order_by_id(broker_order_id)
        return self._map_order(self._client.get_order_by_id(broker_order_id))

    def order(self, broker_order_id: str) -> BrokerOrder:
        if type(broker_order_id) is not str or not broker_order_id:
            raise ValueError("broker_order_id must be a non-empty string")
        return self._map_order(self._client.get_order_by_id(broker_order_id))

    def order_by_client_id(self, client_order_id: str) -> BrokerOrder | None:
        if type(client_order_id) is not str or not client_order_id:
            raise ValueError("client_order_id must be a non-empty string")
        try:
            raw = self._client.get_order_by_client_id(client_order_id)
        except Exception as error:
            status_code = getattr(error, "status_code", None)
            if status_code == 404 or "order not found" in str(error).lower():
                return None
            raise
        return self._map_order(raw)

    @staticmethod
    def _map_order(raw: Any) -> BrokerOrder:
        status_map: dict[str, OrderStatus] = {
            "new": "accepted",
            "accepted": "accepted",
            "pending_new": "submitted",
            "partially_filled": "partially_filled",
            "filled": "filled",
            "canceled": "cancelled",
            "cancelled": "cancelled",
            "expired": "expired",
            "rejected": "rejected",
        }
        raw_status = _value(raw.status).lower()
        if raw_status not in status_map:
            raise PaperBoundaryError("BROKER_ORDER_STATUS_UNSUPPORTED")
        filled_quantity = int(Decimal(str(getattr(raw, "filled_qty", 0))))
        fill_price_raw = getattr(raw, "filled_avg_price", None)
        return BrokerOrder(
            broker_order_id=str(raw.id),
            client_order_id=str(raw.client_order_id),
            symbol=cast(Any, str(raw.symbol)),
            side=cast(Any, _value(raw.side).lower()),
            order_type=cast(Any, _value(raw.type).lower()),
            status=status_map[raw_status],
            quantity=int(Decimal(str(raw.qty))),
            filled_quantity=filled_quantity,
            average_fill_price=(float(Decimal(str(fill_price_raw))) if fill_price_raw else None),
            submitted_at=_timestamp(getattr(raw, "submitted_at", None), name="submitted_at"),
            updated_at=_timestamp(
                getattr(raw, "updated_at", None) or getattr(raw, "submitted_at", None),
                name="updated_at",
            ),
            rejection_reason=getattr(raw, "reject_reason", None),
        )

    @staticmethod
    def _map_position(raw: Any, *, observed_at: datetime) -> BrokerPosition:
        quantity = Decimal(str(raw.qty))
        if quantity != quantity.to_integral_value() or quantity <= 0:
            raise PaperBoundaryError("NON_LONG_INTEGER_POSITION_AT_BROKER")
        return BrokerPosition(
            asset_id=str(raw.asset_id),
            symbol=cast(Any, str(raw.symbol)),
            quantity=int(quantity),
            average_entry_price=float(Decimal(str(raw.avg_entry_price))),
            market_value=_money(raw.market_value, name="position_market_value"),
            observed_at=observed_at,
        )
