"""Conservative, cash-only integer sizing for paper entries."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import ROUND_FLOOR, Decimal


def _decimal(value: float, *, name: str, allow_zero: bool = False) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    converted = Decimal(str(value))
    if not converted.is_finite() or converted < 0 or (converted == 0 and not allow_zero):
        comparison = "non-negative" if allow_zero else "positive"
        raise ValueError(f"{name} must be finite and {comparison}")
    return converted


@dataclass(frozen=True, slots=True)
class SizingRequest:
    available_cash: float
    account_equity: float
    reference_price: float
    stop_distance: float
    strategy_risk_fraction: float
    max_position_fraction: float

    def __post_init__(self) -> None:
        _decimal(self.available_cash, name="available_cash", allow_zero=True)
        _decimal(self.account_equity, name="account_equity", allow_zero=True)
        _decimal(self.reference_price, name="reference_price")
        _decimal(self.stop_distance, name="stop_distance")
        risk_fraction = _decimal(self.strategy_risk_fraction, name="strategy_risk_fraction")
        position_fraction = _decimal(self.max_position_fraction, name="max_position_fraction")
        if risk_fraction > 1:
            raise ValueError("strategy_risk_fraction must not exceed 1")
        if position_fraction > 1:
            raise ValueError("max_position_fraction must not exceed 1")


@dataclass(frozen=True, slots=True)
class SizingResult:
    approved: bool
    reason_code: str
    quantity: int
    required_cash: float
    risk_cash: float
    binding_cap: str


@dataclass(frozen=True, slots=True)
class BalanceFeasibility:
    balance: float
    quantity: int
    reason_code: str
    diagnostic_only: bool = True


def _floor_shares(numerator: Decimal, denominator: Decimal) -> int:
    return int((numerator / denominator).to_integral_value(rounding=ROUND_FLOOR))


def size_long_position(request: SizingRequest) -> SizingResult:
    """Return the smallest cash, position-allocation, and stop-risk share cap."""

    cash = Decimal(str(request.available_cash))
    equity = Decimal(str(request.account_equity))
    price = Decimal(str(request.reference_price))
    stop = Decimal(str(request.stop_distance))
    risk_fraction = Decimal(str(request.strategy_risk_fraction))
    position_fraction = Decimal(str(request.max_position_fraction))

    caps = {
        "cash": _floor_shares(cash, price),
        "position": _floor_shares(equity * position_fraction, price),
        "risk": _floor_shares(equity * risk_fraction, stop),
    }
    binding_cap, quantity = min(caps.items(), key=lambda item: (item[1], item[0]))
    if quantity < 1:
        return SizingResult(
            approved=False,
            reason_code="NO_FEASIBLE_INTEGER_POSITION",
            quantity=0,
            required_cash=0.0,
            risk_cash=0.0,
            binding_cap=binding_cap,
        )
    return SizingResult(
        approved=True,
        reason_code="SIZED_INTEGER_POSITION",
        quantity=quantity,
        required_cash=float(price * quantity),
        risk_cash=float(stop * quantity),
        binding_cap=binding_cap,
    )


def replay_balance_feasibility(
    request: SizingRequest,
    *,
    balances: tuple[float, ...] = (5_000.0, 10_000.0, 25_000.0),
) -> tuple[BalanceFeasibility, ...]:
    """Replay sizing at reporting balances without changing actual broker sizing."""

    diagnostics: list[BalanceFeasibility] = []
    for balance in balances:
        diagnostic_request = replace(
            request,
            available_cash=balance,
            account_equity=balance,
        )
        result = size_long_position(diagnostic_request)
        diagnostics.append(
            BalanceFeasibility(
                balance=float(balance),
                quantity=result.quantity,
                reason_code=result.reason_code,
            )
        )
    return tuple(diagnostics)
