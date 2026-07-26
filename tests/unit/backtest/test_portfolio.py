from collections.abc import Callable

import pytest

from us_intraday_lab.backtest.portfolio import Portfolio


def _assert_invariants(portfolio: Portfolio) -> None:
    assert portfolio.cash >= 0
    assert portfolio.available_cash >= 0
    assert portfolio.equity == pytest.approx(
        portfolio.cash + sum(position.market_value for position in portfolio.positions)
    )
    assert portfolio.equity == pytest.approx(
        portfolio.initial_cash + portfolio.realized_pnl + portfolio.unrealized_pnl
    )
    assert all(position.quantity >= 0 for position in portfolio.positions)
    assert len(portfolio.positions) <= portfolio.max_positions


def _buy(
    portfolio: Portfolio,
    *,
    order_id: str = "buy-SPY",
    symbol: str = "SPY",
    quantity: int = 10,
    price: float = 100.0,
    fees: float = 1.0,
) -> None:
    portfolio.reserve_order(
        order_id=order_id,
        symbol=symbol,
        side="buy",
        quantity=quantity,
        estimated_price=price,
        estimated_fees=fees,
    )
    portfolio.apply_fill(
        order_id=order_id,
        quantity=quantity,
        price=price,
        fees=fees,
    )


def test_buy_mark_and_strategy_sell_reconcile_cash_equity_and_pnl() -> None:
    portfolio = Portfolio(initial_cash=5_000.0)
    _buy(portfolio)

    assert portfolio.cash == pytest.approx(3_999.0)
    assert portfolio.positions[0].average_cost == pytest.approx(100.10)
    assert portfolio.unrealized_pnl == pytest.approx(-1.0)
    _assert_invariants(portfolio)

    portfolio.mark_to_market("SPY", 105.0)
    assert portfolio.unrealized_pnl == pytest.approx(49.0)
    _assert_invariants(portfolio)

    portfolio.reserve_order(
        order_id="sell-SPY",
        symbol="SPY",
        side="sell",
        quantity=10,
        estimated_price=105.0,
    )
    portfolio.apply_fill(
        order_id="sell-SPY",
        quantity=10,
        price=105.0,
        fees=1.0,
        exit_reason="strategy",
    )

    assert portfolio.positions == ()
    assert portfolio.cash == pytest.approx(5_048.0)
    assert portfolio.realized_pnl == pytest.approx(48.0)
    assert portfolio.unrealized_pnl == 0.0
    assert portfolio.fill_events[-1].exit_reason == "strategy"
    _assert_invariants(portfolio)


def test_partial_buy_fill_reduces_reservation_and_cancel_releases_remainder() -> None:
    portfolio = Portfolio(initial_cash=2_000.0)
    portfolio.reserve_order(
        order_id="buy-SPY",
        symbol="SPY",
        side="buy",
        quantity=10,
        estimated_price=100.0,
        estimated_fees=1.0,
    )

    assert portfolio.reserved_cash == pytest.approx(1_001.0)
    assert portfolio.available_cash == pytest.approx(999.0)

    portfolio.apply_fill(
        order_id="buy-SPY",
        quantity=4,
        price=100.0,
        fees=0.4,
    )

    assert portfolio.cash == pytest.approx(1_599.6)
    assert portfolio.reserved_cash == pytest.approx(600.6)
    assert portfolio.reservations[0].remaining_quantity == 6
    assert portfolio.reservations[0].reserved_cash == pytest.approx(600.6)
    _assert_invariants(portfolio)

    portfolio.cancel_order("buy-SPY")

    assert portfolio.reservations == ()
    assert portfolio.reserved_cash == 0.0
    assert portfolio.available_cash == pytest.approx(portfolio.cash)
    assert portfolio.positions[0].quantity == 4
    _assert_invariants(portfolio)


def test_rejection_releases_cash_without_changing_positions_or_pnl() -> None:
    portfolio = Portfolio(initial_cash=2_000.0)
    portfolio.reserve_order(
        order_id="buy-SPY",
        symbol="SPY",
        side="buy",
        quantity=10,
        estimated_price=100.0,
    )

    portfolio.reject_order("buy-SPY")

    assert portfolio.reservations == ()
    assert portfolio.positions == ()
    assert portfolio.cash == 2_000.0
    assert portfolio.realized_pnl == 0.0
    _assert_invariants(portfolio)


def test_sell_reservations_and_fills_cannot_create_a_short_position() -> None:
    portfolio = Portfolio(initial_cash=5_000.0)
    _buy(portfolio, quantity=5, fees=0.0)

    with pytest.raises(ValueError, match="available position quantity"):
        portfolio.reserve_order(
            order_id="oversell",
            symbol="SPY",
            side="sell",
            quantity=6,
            estimated_price=100.0,
        )

    portfolio.reserve_order(
        order_id="sell-four",
        symbol="SPY",
        side="sell",
        quantity=4,
        estimated_price=100.0,
    )
    with pytest.raises(ValueError, match="available position quantity"):
        portfolio.reserve_order(
            order_id="sell-two-more",
            symbol="SPY",
            side="sell",
            quantity=2,
            estimated_price=100.0,
        )
    _assert_invariants(portfolio)


def test_cash_integer_quantity_and_three_position_limit_are_enforced() -> None:
    portfolio = Portfolio(initial_cash=350.0, max_positions=3)

    with pytest.raises(ValueError, match="positive integer"):
        portfolio.reserve_order(
            order_id="fractional",
            symbol="SPY",
            side="buy",
            quantity=1.5,  # type: ignore[arg-type]
            estimated_price=100.0,
        )
    with pytest.raises(ValueError, match="available cash"):
        portfolio.reserve_order(
            order_id="too-expensive",
            symbol="SPY",
            side="buy",
            quantity=4,
            estimated_price=100.0,
        )

    for index, symbol in enumerate(("SPY", "QQQ", "IWM"), start=1):
        _buy(
            portfolio,
            order_id=f"buy-{symbol}",
            symbol=symbol,
            quantity=1,
            price=100.0,
            fees=0.0,
        )
        assert len(portfolio.positions) == index

    with pytest.raises(ValueError, match="maximum concurrent positions"):
        portfolio.reserve_order(
            order_id="fourth",
            symbol="DIA",
            side="buy",
            quantity=1,
            estimated_price=10.0,
        )
    _assert_invariants(portfolio)


def test_fill_that_would_consume_cash_reserved_for_other_orders_is_atomic() -> None:
    portfolio = Portfolio(initial_cash=1_000.0)
    portfolio.reserve_order(
        order_id="buy-SPY",
        symbol="SPY",
        side="buy",
        quantity=5,
        estimated_price=100.0,
    )
    portfolio.reserve_order(
        order_id="buy-QQQ",
        symbol="QQQ",
        side="buy",
        quantity=5,
        estimated_price=100.0,
    )

    with pytest.raises(ValueError, match="available cash"):
        portfolio.apply_fill(
            order_id="buy-SPY",
            quantity=5,
            price=101.0,
            fees=0.0,
        )

    assert portfolio.cash == 1_000.0
    assert portfolio.reserved_cash == 1_000.0
    assert portfolio.positions == ()
    _assert_invariants(portfolio)


def test_end_of_day_liquidation_is_distinct_from_strategy_exit() -> None:
    portfolio = Portfolio(initial_cash=5_000.0)
    _buy(portfolio, quantity=5, fees=0.0)

    portfolio.force_close("SPY", price=101.0, fees=0.25)

    assert portfolio.positions == ()
    assert portfolio.fill_events[-1].side == "sell"
    assert portfolio.fill_events[-1].exit_reason == "end_of_day"
    assert portfolio.fill_events[-1].forced is True
    _assert_invariants(portfolio)


def _sequence_full_buy(portfolio: Portfolio) -> None:
    _buy(portfolio, fees=0.5)


def _sequence_partial_then_cancel(portfolio: Portfolio) -> None:
    portfolio.reserve_order(
        order_id="buy-SPY",
        symbol="SPY",
        side="buy",
        quantity=10,
        estimated_price=100.0,
    )
    portfolio.apply_fill(order_id="buy-SPY", quantity=3, price=100.0, fees=0.3)
    portfolio.cancel_order("buy-SPY")


def _sequence_buy_then_sell(portfolio: Portfolio) -> None:
    _buy(portfolio, fees=0.5)
    portfolio.reserve_order(
        order_id="sell-SPY",
        symbol="SPY",
        side="sell",
        quantity=10,
        estimated_price=102.0,
    )
    portfolio.apply_fill(
        order_id="sell-SPY",
        quantity=10,
        price=102.0,
        fees=0.5,
        exit_reason="strategy",
    )


def _sequence_rejection(portfolio: Portfolio) -> None:
    portfolio.reserve_order(
        order_id="buy-SPY",
        symbol="SPY",
        side="buy",
        quantity=10,
        estimated_price=100.0,
    )
    portfolio.reject_order("buy-SPY")


def _sequence_forced_close(portfolio: Portfolio) -> None:
    _buy(portfolio, fees=0.5)
    portfolio.force_close("SPY", price=99.0, fees=0.5)


@pytest.mark.parametrize(
    "event_sequence",
    [
        _sequence_full_buy,
        _sequence_partial_then_cancel,
        _sequence_buy_then_sell,
        _sequence_rejection,
        _sequence_forced_close,
    ],
    ids=["buy", "partial-cancel", "sell", "rejection", "forced-close"],
)
def test_property_style_event_sequences_preserve_accounting_invariants(
    event_sequence: Callable[[Portfolio], None],
) -> None:
    portfolio = Portfolio(initial_cash=5_000.0)

    event_sequence(portfolio)

    _assert_invariants(portfolio)
