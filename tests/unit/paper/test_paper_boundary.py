from __future__ import annotations

import inspect
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from tests.fakes.broker import FakePaperBroker, SubmitBehavior
from us_intraday_lab.cli import app
from us_intraday_lab.contracts.market import MarketBarClosed
from us_intraday_lab.contracts.orders import OrderIntent
from us_intraday_lab.contracts.paper import (
    BrokerAccount,
    BrokerClock,
    BrokerOrder,
    BrokerPosition,
    PaperCheckpoint,
    PositionSnapshot,
    RiskDecision,
)
from us_intraday_lab.contracts.reports import DailyPaperReport
from us_intraday_lab.paper.alpaca_paper import (
    ALPACA_PAPER_ENDPOINT,
    AlpacaPaperBroker,
    AlpacaPaperConfig,
    PaperBoundaryError,
)
from us_intraday_lab.paper.broker import PaperBroker

NOW = datetime(2026, 8, 3, 14, 0, tzinfo=UTC)


def _raw_account(**overrides: Any) -> SimpleNamespace:
    values = {
        "id": "account-id",
        "account_number": "PA123",
        "status": "ACTIVE",
        "currency": "USD",
        "cash": "25000.00",
        "buying_power": "25000.00",
        "equity": "25000.00",
        "trading_blocked": False,
        "account_blocked": False,
        "trade_suspended_by_user": False,
        "multiplier": "1",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _raw_order(**overrides: Any) -> SimpleNamespace:
    values = {
        "id": "sdk-order-1",
        "client_order_id": "intent-1",
        "symbol": "SPY",
        "side": "buy",
        "type": "market",
        "status": "new",
        "qty": "10",
        "filled_qty": "0",
        "filled_avg_price": None,
        "submitted_at": NOW,
        "updated_at": NOW,
        "reject_reason": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _SdkClient:
    def __init__(self, account: SimpleNamespace | None = None) -> None:
        self._account = account or _raw_account()
        self._base_url = ALPACA_PAPER_ENDPOINT
        self.orders: list[SimpleNamespace] = []
        self.position_rows: list[SimpleNamespace] = []
        self.submitted_requests: list[Any] = []
        self.cancelled_order_ids: list[str] = []

    def get_account(self) -> SimpleNamespace:
        return self._account

    def get_clock(self) -> SimpleNamespace:
        return SimpleNamespace(
            timestamp=NOW,
            is_open=True,
            next_open=NOW + timedelta(days=1),
            next_close=NOW + timedelta(hours=6),
        )

    def get_orders(self, *, filter: object) -> list[SimpleNamespace]:
        del filter
        return self.orders

    def get_all_positions(self) -> list[SimpleNamespace]:
        return self.position_rows

    def submit_order(self, *, order_data: Any) -> SimpleNamespace:
        self.submitted_requests.append(order_data)
        order = _raw_order(
            id=f"sdk-order-{len(self.orders) + 1}",
            client_order_id=order_data.client_order_id,
            symbol=order_data.symbol,
            side=order_data.side,
            type=order_data.type,
            qty=order_data.qty,
        )
        self.orders.append(order)
        return order

    def cancel_order_by_id(self, order_id: str) -> None:
        self.cancelled_order_ids.append(order_id)
        for order in self.orders:
            if order.id == order_id:
                order.status = "canceled"

    def get_order_by_id(self, order_id: str) -> SimpleNamespace:
        return next(item for item in self.orders if item.id == order_id)


def _connect(
    account: SimpleNamespace | None = None,
) -> tuple[AlpacaPaperBroker, list[dict[str, object]], _SdkClient]:
    calls: list[dict[str, object]] = []
    client = _SdkClient(account)

    def factory(**kwargs: object) -> _SdkClient:
        calls.append(kwargs)
        return client

    broker = AlpacaPaperBroker.from_environment(
        environ={
            "ALPACA_PAPER_API_KEY": "paper-key",
            "ALPACA_PAPER_SECRET_KEY": "paper-secret",
        },
        client_factory=factory,
    )
    return broker, calls, client


def _intent(key: str = "intent-1") -> OrderIntent:
    return OrderIntent(
        schema_version="1.0.0",
        run_id="paper-session-1",
        strategy_id="strategy-1",
        symbol="SPY",
        session=date(2026, 8, 3),
        side="buy",
        order_type="market",
        quantity=10,
        signal_time=NOW,
        eligible_time=NOW + timedelta(minutes=1),
        reason_code="entry_signal",
        idempotency_key=key,
    )


def test_config_accepts_only_the_exact_alpaca_paper_endpoint() -> None:
    assert AlpacaPaperConfig().endpoint == ALPACA_PAPER_ENDPOINT
    with pytest.raises(ValidationError):
        AlpacaPaperConfig(endpoint="https://api.alpaca.markets")
    with pytest.raises(ValidationError):
        AlpacaPaperConfig(endpoint="https://proxy.invalid")


def test_connection_uses_only_paper_credentials_and_forces_sdk_paper_mode() -> None:
    broker, calls, _client = _connect()
    assert broker.endpoint == ALPACA_PAPER_ENDPOINT
    account = broker.account()
    assert account.environment == "paper"
    lock = Path(__file__).resolve().parents[3] / "requirements-paper.lock"
    assert f"alpaca-py=={account.broker_sdk_version}" in lock.read_text(encoding="utf-8")
    assert calls == [
        {
            "api_key": "paper-key",
            "secret_key": "paper-secret",
            "paper": True,
        }
    ]

    with pytest.raises(PaperBoundaryError, match="ALPACA_PAPER_API_KEY"):
        AlpacaPaperBroker.from_environment(
            environ={
                "APCA_API_KEY_ID": "live-looking-key",
                "APCA_API_SECRET_KEY": "live-looking-secret",
            },
            client_factory=lambda **_kwargs: _SdkClient(),
        )


def test_injected_client_must_also_prove_the_exact_paper_endpoint() -> None:
    def unsafe_factory(**_kwargs: object) -> _SdkClient:
        client = _SdkClient()
        client._base_url = "https://api.alpaca.markets"
        return client

    with pytest.raises(PaperBoundaryError, match="PAPER_ENDPOINT_MISMATCH"):
        AlpacaPaperBroker.from_environment(
            environ={
                "ALPACA_PAPER_API_KEY": "paper-key",
                "ALPACA_PAPER_SECRET_KEY": "paper-secret",
            },
            client_factory=unsafe_factory,
        )


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"status": "CLOSED"}, "ACCOUNT_NOT_ACTIVE"),
        ({"trading_blocked": True}, "ACCOUNT_TRADING_BLOCKED"),
        ({"account_blocked": True}, "ACCOUNT_BLOCKED"),
        ({"trade_suspended_by_user": True}, "ACCOUNT_TRADING_SUSPENDED"),
        ({"currency": "EUR"}, "ACCOUNT_NOT_USD"),
    ],
)
def test_connection_rejects_unsafe_account_responses(
    overrides: dict[str, object], reason: str
) -> None:
    with pytest.raises(PaperBoundaryError, match=reason):
        _connect(_raw_account(**overrides))


def test_adapter_maps_only_the_minimal_paper_protocol_operations() -> None:
    broker, _calls, client = _connect()
    client.orders.append(_raw_order())
    client.position_rows.append(
        SimpleNamespace(
            asset_id="asset-spy",
            symbol="SPY",
            qty="10",
            avg_entry_price="100.00",
            market_value="1005.00",
        )
    )

    assert broker.clock().environment == "paper"
    assert broker.open_orders()[0].client_order_id == "intent-1"
    assert broker.positions()[0].quantity == 10
    submitted = broker.submit(_intent("new-intent"))
    assert submitted.client_order_id == "new-intent"
    assert client.submitted_requests[0].client_order_id == "new-intent"
    cancelled = broker.cancel(submitted.broker_order_id)
    assert cancelled.status == "cancelled"
    assert client.cancelled_order_ids == [submitted.broker_order_id]


def test_public_config_and_cli_expose_no_live_or_endpoint_override_switch() -> None:
    schema = str(AlpacaPaperConfig.model_json_schema()).lower()
    signature = str(inspect.signature(AlpacaPaperBroker.from_environment)).lower()
    constructor = str(inspect.signature(AlpacaPaperBroker)).lower()
    cli_help = CliRunner().invoke(app, ["--help"])
    assert cli_help.exit_code == 0
    for forbidden in ("trading_live", "live_url", "url_override", "base_url"):
        assert forbidden not in schema
        assert forbidden not in signature
        assert forbidden not in constructor
        assert forbidden not in cli_help.stdout.lower()
    assert "api_key" not in constructor
    assert "secret_key" not in constructor


def test_market_and_paper_contracts_are_frozen_versioned_and_utc() -> None:
    bar = MarketBarClosed(
        provider_event_id="alpaca:SPY:2026-08-03T14:00:00Z",
        symbol="SPY",
        timeframe="15min",
        bar_start=NOW,
        bar_end=NOW + timedelta(minutes=15),
        available_at=NOW + timedelta(minutes=15),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
        volume=1000,
    )
    assert bar.schema_version == "1.0.0"
    assert (bar.provider, bar.feed) == ("alpaca", "iex")
    with pytest.raises(ValidationError):
        bar.close = 1.0  # type: ignore[misc]
    with pytest.raises(ValidationError, match="timezone-aware UTC"):
        MarketBarClosed.model_validate(
            {**bar.model_dump(), "available_at": NOW.replace(tzinfo=None)}
        )

    account = BrokerAccount(
        account_id="account-1",
        account_number="PA123",
        broker_sdk_version="test-sdk-1.0",
        status="ACTIVE",
        cash=25_000,
        buying_power=25_000,
        equity=25_000,
        trading_blocked=False,
        account_blocked=False,
        trade_suspended_by_user=False,
        multiplier=1,
        observed_at=NOW,
    )
    clock = BrokerClock(
        observed_at=NOW,
        is_open=True,
        next_open=NOW + timedelta(days=1),
        next_close=NOW + timedelta(hours=6),
    )
    position = BrokerPosition(
        asset_id="asset-spy",
        symbol="SPY",
        quantity=10,
        average_entry_price=100,
        market_value=1005,
        observed_at=NOW,
    )
    order = BrokerOrder(
        broker_order_id="order-1",
        client_order_id="intent-1",
        symbol="SPY",
        side="buy",
        order_type="market",
        status="accepted",
        quantity=10,
        filled_quantity=0,
        average_fill_price=None,
        submitted_at=NOW,
        updated_at=NOW,
        rejection_reason=None,
    )
    snapshot = PositionSnapshot(
        snapshot_id="snapshot-1",
        paper_session_id="session-1",
        positions=(position,),
        observed_at=NOW,
    )
    checkpoint = PaperCheckpoint(
        checkpoint_id="checkpoint-1",
        paper_session_id="session-1",
        event_sequence=1,
        state_sha256="a" * 64,
        created_at=NOW,
    )
    decision = RiskDecision(
        decision_id="risk-1",
        idempotency_key="intent-1",
        approved=True,
        reason_code="RISK_APPROVED",
        observed_values={"cash": 25_000.0},
        decided_at=NOW,
    )
    report = DailyPaperReport(
        report_id="report-1",
        paper_session_id="session-1",
        session_date=date(2026, 8, 3),
        generated_at=NOW,
        account=account,
        final_positions=snapshot,
        orders=(order,),
        risk_decisions=(decision,),
        incident_codes=(),
        net_pnl=5.0,
    )
    assert clock.environment == "paper"
    assert checkpoint.state_sha256 == "a" * 64
    assert report.final_positions.positions == (position,)


def test_fake_broker_implements_required_deterministic_faults() -> None:
    broker: PaperBroker = FakePaperBroker(now=NOW)
    assert broker.account().environment == "paper"
    assert broker.open_orders() == ()
    assert broker.positions() == ()

    accepted = broker.submit(_intent("accepted"))
    assert accepted.status == "accepted"
    assert broker.submit(_intent("accepted")) == accepted

    fake = broker
    assert isinstance(fake, FakePaperBroker)
    fake.queue_submit_behavior(SubmitBehavior.REJECT)
    assert fake.submit(_intent("rejected")).status == "rejected"
    fake.queue_submit_behavior(SubmitBehavior.PARTIAL_FILL)
    assert fake.submit(_intent("partial")).status == "partially_filled"
    fake.queue_submit_behavior(SubmitBehavior.DELAYED_FILL)
    assert fake.submit(_intent("delayed")).status == "submitted"
    fake.force_position(symbol="QQQ", quantity=2, price=400.0)
    assert fake.positions()[0].symbol == "QQQ"
    fake.set_stale_clock(timedelta(minutes=10))
    assert fake.clock().observed_at == NOW - timedelta(minutes=10)
    fake.disconnect()
    with pytest.raises(ConnectionError, match="FAKE_BROKER_DISCONNECTED"):
        fake.account()


def test_broker_protocol_has_no_arbitrary_request_or_endpoint_mutation() -> None:
    public = {
        name
        for name, value in inspect.getmembers(PaperBroker)
        if callable(value) and not name.startswith("_")
    }
    assert public == {"account", "clock", "open_orders", "positions", "submit", "cancel"}
    assert not hasattr(PaperBroker, "request")
    assert not hasattr(PaperBroker, "set_endpoint")


def test_source_tree_contains_no_real_money_endpoint_literal() -> None:
    root = Path(__file__).resolve().parents[3]
    production_endpoint = "https://" + "api.alpaca.markets"
    for path in (root / "src").rglob("*.py"):
        assert production_endpoint not in path.read_text(encoding="utf-8")
