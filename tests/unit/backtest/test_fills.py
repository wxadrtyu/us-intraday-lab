from datetime import UTC, date, datetime, timedelta

import pytest

from us_intraday_lab.backtest.costs import COST_SCENARIOS, CostModel
from us_intraday_lab.backtest.fills import Fill, FillError, FillSimulator, MinuteBar
from us_intraday_lab.contracts.orders import OrderIntent

SIGNAL_TIME = datetime(2026, 7, 2, 14, 0, tzinfo=UTC)
ELIGIBLE_TIME = SIGNAL_TIME + timedelta(minutes=1)


def _order(
    *,
    side: str = "buy",
    order_type: str = "market",
    limit_price: float | None = None,
    eligible_time: datetime = ELIGIBLE_TIME,
) -> OrderIntent:
    return OrderIntent(
        schema_version="1.0.0",
        run_id="run-001",
        strategy_id="strategy-001",
        symbol="SPY",
        session=date(2026, 7, 2),
        side=side,
        order_type=order_type,
        quantity=10,
        limit_price=limit_price,
        signal_time=SIGNAL_TIME,
        eligible_time=eligible_time,
        reason_code="entry_signal" if side == "buy" else "exit_signal",
        idempotency_key=f"run-001:SPY:{SIGNAL_TIME.isoformat()}:{side}",
    )


def _bar(
    timestamp: datetime,
    *,
    open_: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
) -> MinuteBar:
    return MinuteBar(
        symbol="SPY",
        timestamp=timestamp,
        open=open_,
        high=high,
        low=low,
        close=close,
    )


class _ForgedString(str):
    pass


def _forged_order(**overrides: object) -> OrderIntent:
    payload = _order().model_dump()
    payload.update(overrides)
    return OrderIntent.model_construct(**payload)


@pytest.mark.parametrize(
    "side",
    ["hold", "short", "arbitrary", True, _ForgedString("buy")],
)
def test_forged_order_side_fails_closed_before_timing_or_fill_logic(side: object) -> None:
    simulator = FillSimulator(COST_SCENARIOS["base"])
    forged = _forged_order(side=side)

    with pytest.raises(FillError, match="side"):
        simulator.try_fill(forged, _bar(SIGNAL_TIME))


@pytest.mark.parametrize(
    "order_type",
    ["stop", "unknown", True, _ForgedString("market")],
)
def test_forged_order_type_fails_closed_before_timing_or_fill_logic(
    order_type: object,
) -> None:
    simulator = FillSimulator(COST_SCENARIOS["base"])
    forged = _forged_order(order_type=order_type)

    with pytest.raises(FillError, match="order_type"):
        simulator.try_fill(forged, _bar(SIGNAL_TIME))


@pytest.mark.parametrize(
    ("side", "order_type"),
    [
        ("hold", "market"),
        ("buy", "stop"),
        (_ForgedString("buy"), "market"),
        ("buy", _ForgedString("limit")),
    ],
)
def test_public_fill_rejects_invalid_or_forged_literals(
    side: object,
    order_type: object,
) -> None:
    with pytest.raises(FillError):
        Fill(
            order_key="order-1",
            symbol="SPY",
            side=side,  # type: ignore[arg-type]
            order_type=order_type,  # type: ignore[arg-type]
            quantity=1,
            price=100.0,
            fees=0.0,
            fill_time=ELIGIBLE_TIME,
        )


@pytest.mark.parametrize("value", [True, "100.0", 1j, float("nan"), float("inf")])
def test_minute_bar_rejects_boolean_and_non_real_prices(value: object) -> None:
    with pytest.raises(ValueError, match="exact int or float|finite"):
        MinuteBar(
            symbol="SPY",
            timestamp=ELIGIBLE_TIME,
            open=value,  # type: ignore[arg-type]
            high=value,  # type: ignore[arg-type]
            low=value,  # type: ignore[arg-type]
            close=value,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("quantity", True),
        ("price", True),
        ("fees", True),
        ("price", "100.0"),
        ("fees", 1j),
        ("price", float("inf")),
        ("fees", float("nan")),
    ],
)
def test_public_fill_rejects_boolean_and_non_real_numeric_fields(
    field: str,
    value: object,
) -> None:
    values: dict[str, object] = {
        "order_key": "order-1",
        "symbol": "SPY",
        "side": "buy",
        "order_type": "market",
        "quantity": 1,
        "price": 100.0,
        "fees": 0.0,
        "fill_time": ELIGIBLE_TIME,
    }
    values[field] = value

    with pytest.raises(
        ValueError,
        match="exact int or float|positive integer|finite",
    ):
        Fill(**values)  # type: ignore[arg-type]


def test_market_order_cannot_fill_on_signal_bar() -> None:
    simulator = FillSimulator(COST_SCENARIOS["base"])

    fill = simulator.try_fill(_order(), _bar(SIGNAL_TIME))

    assert fill is None


@pytest.mark.parametrize(("side", "direction"), [("buy", 1.0), ("sell", -1.0)])
def test_market_order_fills_at_eligible_open_with_adverse_spread_and_slippage(
    side: str, direction: float
) -> None:
    model = CostModel(
        model_id="test-cost-1.0.0",
        half_spread_bps=1.0,
        slippage_bps=2.0,
        commission_per_share_usd=0.01,
    )
    simulator = FillSimulator(model)

    fill = simulator.try_fill(_order(side=side), _bar(ELIGIBLE_TIME))

    assert fill is not None
    assert fill.price == pytest.approx(100.0 * (1 + direction * 3.0 / 10_000))
    assert fill.quantity == 10
    assert fill.fees == pytest.approx(0.10)
    assert fill.fill_time == ELIGIBLE_TIME


def test_market_order_waits_until_eligible_bar() -> None:
    simulator = FillSimulator(COST_SCENARIOS["base"])
    before_eligible = ELIGIBLE_TIME - timedelta(seconds=1)

    assert simulator.try_fill(_order(), _bar(before_eligible)) is None


@pytest.mark.parametrize(
    ("side", "open_", "high", "low"),
    [
        ("buy", 100.5, 101.0, 100.01),
        ("sell", 99.5, 99.99, 99.0),
    ],
)
def test_limit_order_does_not_fill_unless_eligible_range_crosses_limit(
    side: str, open_: float, high: float, low: float
) -> None:
    simulator = FillSimulator(COST_SCENARIOS["base"])

    fill = simulator.try_fill(
        _order(side=side, order_type="limit", limit_price=100.0),
        _bar(ELIGIBLE_TIME, open_=open_, high=high, low=low, close=open_),
    )

    assert fill is None


@pytest.mark.parametrize(
    ("side", "open_", "high", "low"),
    [
        ("buy", 99.0, 102.0, 98.0),
        ("sell", 101.0, 102.0, 98.0),
    ],
)
def test_crossed_limit_uses_limit_as_conservative_ambiguous_ohlc_price(
    side: str, open_: float, high: float, low: float
) -> None:
    simulator = FillSimulator(COST_SCENARIOS["stress"])

    fill = simulator.try_fill(
        _order(side=side, order_type="limit", limit_price=100.0),
        _bar(ELIGIBLE_TIME, open_=open_, high=high, low=low),
    )

    assert fill is not None
    assert fill.price == 100.0


def test_limit_order_cannot_fill_on_signal_bar_even_when_crossed() -> None:
    simulator = FillSimulator(COST_SCENARIOS["base"])

    fill = simulator.try_fill(
        _order(order_type="limit", limit_price=100.0),
        _bar(SIGNAL_TIME, high=101.0, low=99.0),
    )

    assert fill is None


def test_fill_rejects_intent_without_strict_next_bar_eligibility() -> None:
    simulator = FillSimulator(COST_SCENARIOS["base"])
    invalid_timing = _order(eligible_time=SIGNAL_TIME)

    with pytest.raises(ValueError, match="eligible_time must be at least one minute"):
        simulator.try_fill(invalid_timing, _bar(SIGNAL_TIME))


def test_fill_rejects_sub_minute_eligibility_even_on_a_later_timestamp() -> None:
    simulator = FillSimulator(COST_SCENARIOS["base"])
    too_early = SIGNAL_TIME + timedelta(seconds=30)

    with pytest.raises(ValueError, match="eligible_time must be at least one minute"):
        simulator.try_fill(_order(eligible_time=too_early), _bar(too_early))
