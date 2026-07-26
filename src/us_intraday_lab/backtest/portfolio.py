"""Long-only integer-share portfolio and reservation accounting."""

from dataclasses import dataclass, replace
from math import isfinite
from typing import Final, Literal, cast

OrderSide = Literal["buy", "sell"]
ExitReason = Literal["strategy", "end_of_day"]
MONEY_EPSILON: Final = 1e-12


def _positive_integer(value: int, *, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _exact_finite_number(value: object, *, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be an exact int or float")
    normalized = float(cast("int | float", value))
    if not isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


def _non_negative_money(value: float, *, name: str) -> float:
    normalized = _exact_finite_number(value, name=name)
    if normalized < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return normalized


def _positive_price(value: float, *, name: str = "price") -> float:
    normalized = _exact_finite_number(value, name=name)
    if normalized <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return normalized


def _normalized_nonnegative_residual(value: float, *, name: str) -> float:
    if value < -MONEY_EPSILON:
        raise ValueError(f"{name} must not be negative")
    return 0.0 if abs(value) <= MONEY_EPSILON else value


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: int
    average_cost: float
    market_price: float

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must be non-empty")
        _positive_integer(self.quantity, name="quantity")
        object.__setattr__(
            self,
            "average_cost",
            _positive_price(self.average_cost, name="average_cost"),
        )
        object.__setattr__(
            self,
            "market_price",
            _positive_price(self.market_price, name="market_price"),
        )

    @property
    def cost_basis(self) -> float:
        return self.quantity * self.average_cost

    @property
    def market_value(self) -> float:
        return self.quantity * self.market_price

    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.cost_basis


@dataclass(frozen=True)
class Reservation:
    order_id: str
    symbol: str
    side: OrderSide
    remaining_quantity: int
    reserved_cash: float

    def __post_init__(self) -> None:
        if not self.order_id or not self.symbol:
            raise ValueError("order_id and symbol must be non-empty")
        if type(self.side) is not str or self.side not in ("buy", "sell"):
            raise ValueError("side must be exactly 'buy' or 'sell'")
        _positive_integer(self.remaining_quantity, name="remaining_quantity")
        object.__setattr__(
            self,
            "reserved_cash",
            _non_negative_money(self.reserved_cash, name="reserved_cash"),
        )


@dataclass(frozen=True)
class PortfolioFill:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: int
    price: float
    fees: float
    exit_reason: ExitReason | None
    forced: bool

    def __post_init__(self) -> None:
        if not self.order_id or not self.symbol:
            raise ValueError("order_id and symbol must be non-empty")
        if type(self.side) is not str or self.side not in ("buy", "sell"):
            raise ValueError("side must be exactly 'buy' or 'sell'")
        _positive_integer(self.quantity, name="quantity")
        object.__setattr__(self, "price", _positive_price(self.price))
        object.__setattr__(self, "fees", _non_negative_money(self.fees, name="fees"))
        if self.exit_reason is not None and (
            type(self.exit_reason) is not str or self.exit_reason not in ("strategy", "end_of_day")
        ):
            raise ValueError("unsupported exit_reason")
        if type(self.forced) is not bool:
            raise ValueError("forced must be a bool")


class Portfolio:
    """Mutable account state with atomic reservation-aware fills."""

    def __init__(self, initial_cash: float, *, max_positions: int = 3) -> None:
        normalized_initial_cash = _non_negative_money(initial_cash, name="initial_cash")
        _positive_integer(max_positions, name="max_positions")
        self.initial_cash = normalized_initial_cash
        self.max_positions = max_positions
        self._cash = normalized_initial_cash
        self._realized_pnl = 0.0
        self._positions: dict[str, Position] = {}
        self._reservations: dict[str, Reservation] = {}
        self._fill_events: list[PortfolioFill] = []

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def reserved_cash(self) -> float:
        return sum(reservation.reserved_cash for reservation in self._reservations.values())

    @property
    def available_cash(self) -> float:
        return _normalized_nonnegative_residual(
            self.cash - self.reserved_cash,
            name="available cash",
        )

    @property
    def positions(self) -> tuple[Position, ...]:
        return tuple(self._positions[symbol] for symbol in sorted(self._positions))

    @property
    def reservations(self) -> tuple[Reservation, ...]:
        return tuple(self._reservations[order_id] for order_id in sorted(self._reservations))

    @property
    def fill_events(self) -> tuple[PortfolioFill, ...]:
        return tuple(self._fill_events)

    @property
    def equity(self) -> float:
        return self.cash + sum(position.market_value for position in self._positions.values())

    @property
    def realized_pnl(self) -> float:
        return self._realized_pnl

    @property
    def unrealized_pnl(self) -> float:
        return sum(position.unrealized_pnl for position in self._positions.values())

    def reserve_order(
        self,
        *,
        order_id: str,
        symbol: str,
        side: OrderSide,
        quantity: int,
        estimated_price: float,
        estimated_fees: float = 0.0,
    ) -> None:
        if not order_id:
            raise ValueError("order_id must be non-empty")
        if order_id in self._reservations:
            raise ValueError(f"duplicate reservation: {order_id}")
        if not symbol:
            raise ValueError("symbol must be non-empty")
        if side not in ("buy", "sell"):
            raise ValueError("side must be buy or sell")
        _positive_integer(quantity, name="quantity")
        estimated_price = _positive_price(estimated_price, name="estimated_price")
        estimated_fees = _non_negative_money(estimated_fees, name="estimated_fees")

        reserved_cash = 0.0
        if side == "buy":
            occupied_symbols = set(self._positions)
            occupied_symbols.update(
                reservation.symbol
                for reservation in self._reservations.values()
                if reservation.side == "buy"
            )
            if symbol not in occupied_symbols and len(occupied_symbols) >= self.max_positions:
                raise ValueError("maximum concurrent positions would be exceeded")
            reserved_cash = quantity * estimated_price + estimated_fees
            available_cash = self.available_cash
            if reserved_cash > available_cash + MONEY_EPSILON:
                raise ValueError("order exceeds available cash")
            reserved_cash = min(reserved_cash, available_cash)
        else:
            position = self._positions.get(symbol)
            held_quantity = 0 if position is None else position.quantity
            already_reserved = sum(
                reservation.remaining_quantity
                for reservation in self._reservations.values()
                if reservation.side == "sell" and reservation.symbol == symbol
            )
            if quantity > held_quantity - already_reserved:
                raise ValueError("order exceeds available position quantity")

        self._reservations[order_id] = Reservation(
            order_id=order_id,
            symbol=symbol,
            side=side,
            remaining_quantity=quantity,
            reserved_cash=reserved_cash,
        )

    def apply_fill(
        self,
        *,
        order_id: str,
        quantity: int,
        price: float,
        fees: float = 0.0,
        exit_reason: ExitReason | None = None,
    ) -> None:
        _positive_integer(quantity, name="quantity")
        price = _positive_price(price)
        fees = _non_negative_money(fees, name="fees")
        if exit_reason not in (None, "strategy", "end_of_day"):
            raise ValueError("unsupported exit_reason")
        reservation = self._reservation(order_id)
        if quantity > reservation.remaining_quantity:
            raise ValueError("fill quantity exceeds reservation remainder")

        remaining_quantity = reservation.remaining_quantity - quantity
        next_position: Position | None
        if reservation.side == "buy":
            released_cash = (
                reservation.reserved_cash
                if remaining_quantity == 0
                else reservation.reserved_cash * quantity / reservation.remaining_quantity
            )
            remaining_reserved_cash = reservation.reserved_cash - released_cash
            remaining_reserved_cash = _normalized_nonnegative_residual(
                remaining_reserved_cash,
                name="remaining reserved cash",
            )
            post_fill_reserved_cash = (
                self.reserved_cash - reservation.reserved_cash + remaining_reserved_cash
            )
            cash_delta = -(quantity * price + fees)
            next_cash = self.cash + cash_delta
            if next_cash < post_fill_reserved_cash - MONEY_EPSILON:
                raise ValueError("fill exceeds available cash after remaining reservations")
            next_cash = _normalized_nonnegative_residual(next_cash, name="cash")

            current = self._positions.get(reservation.symbol)
            current_quantity = 0 if current is None else current.quantity
            current_cost_basis = 0.0 if current is None else current.cost_basis
            next_quantity = current_quantity + quantity
            next_cost_basis = current_cost_basis + quantity * price + fees
            next_position = Position(
                symbol=reservation.symbol,
                quantity=next_quantity,
                average_cost=next_cost_basis / next_quantity,
                market_price=price,
            )
            realized_delta = 0.0
            event_exit_reason: ExitReason | None = None
        else:
            remaining_reserved_cash = 0.0
            current = self._positions.get(reservation.symbol)
            if current is None or quantity > current.quantity:
                raise ValueError("fill would create a short position")
            cash_delta = quantity * price - fees
            next_cash = self.cash + cash_delta
            if next_cash < -MONEY_EPSILON:
                raise ValueError("fill would make cash negative")
            next_cash = _normalized_nonnegative_residual(next_cash, name="cash")
            next_quantity = current.quantity - quantity
            next_position = (
                None
                if next_quantity == 0
                else replace(current, quantity=next_quantity, market_price=price)
            )
            realized_delta = quantity * (price - current.average_cost) - fees
            event_exit_reason = "strategy" if exit_reason is None else exit_reason

        if remaining_quantity == 0:
            del self._reservations[order_id]
        else:
            self._reservations[order_id] = replace(
                reservation,
                remaining_quantity=remaining_quantity,
                reserved_cash=remaining_reserved_cash,
            )
        self._cash = next_cash
        self._realized_pnl += realized_delta
        if next_position is None:
            del self._positions[reservation.symbol]
        else:
            self._positions[reservation.symbol] = next_position
        self._fill_events.append(
            PortfolioFill(
                order_id=order_id,
                symbol=reservation.symbol,
                side=reservation.side,
                quantity=quantity,
                price=price,
                fees=fees,
                exit_reason=event_exit_reason,
                forced=event_exit_reason == "end_of_day",
            )
        )

    def cancel_order(self, order_id: str) -> None:
        self._reservation(order_id)
        del self._reservations[order_id]

    def reject_order(self, order_id: str) -> None:
        self.cancel_order(order_id)

    def mark_to_market(self, symbol: str, price: float) -> None:
        price = _positive_price(price)
        position = self._positions.get(symbol)
        if position is None:
            raise ValueError(f"position not found: {symbol}")
        self._positions[symbol] = replace(position, market_price=price)

    def force_close(self, symbol: str, *, price: float, fees: float = 0.0) -> None:
        price = _positive_price(price)
        fees = _non_negative_money(fees, name="fees")
        position = self._positions.get(symbol)
        if position is None:
            raise ValueError(f"position not found: {symbol}")
        for order_id in tuple(self._reservations):
            if self._reservations[order_id].symbol == symbol:
                self.cancel_order(order_id)
        order_id = f"end-of-day:{symbol}:{len(self._fill_events)}"
        self.reserve_order(
            order_id=order_id,
            symbol=symbol,
            side="sell",
            quantity=position.quantity,
            estimated_price=price,
            estimated_fees=fees,
        )
        self.apply_fill(
            order_id=order_id,
            quantity=position.quantity,
            price=price,
            fees=fees,
            exit_reason="end_of_day",
        )

    def _reservation(self, order_id: str) -> Reservation:
        try:
            return self._reservations[order_id]
        except KeyError as exc:
            raise ValueError(f"reservation not found: {order_id}") from exc
