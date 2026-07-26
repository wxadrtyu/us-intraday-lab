"""Descriptive backtest metrics with explicit session-level sampling."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from math import isfinite, sqrt
from statistics import fmean, stdev

TRADING_SESSIONS_PER_YEAR = 252.0


def _finite(value: float, *, name: str) -> float:
    normalized = float(value)
    if not isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


def _utc(value: datetime, *, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class TradeRecord:
    symbol: str
    session: date
    quantity: int
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    gross_pnl: float
    net_pnl: float
    cost_paid: float
    forced: bool

    def __post_init__(self) -> None:
        if not self.symbol:
            raise ValueError("symbol must be non-empty")
        if type(self.session) is not date:
            raise TypeError("session must be an exact date")
        if type(self.quantity) is not int or self.quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        entry_time = _utc(self.entry_time, name="entry_time")
        exit_time = _utc(self.exit_time, name="exit_time")
        if exit_time < entry_time:
            raise ValueError("exit_time must not precede entry_time")
        object.__setattr__(self, "entry_time", entry_time)
        object.__setattr__(self, "exit_time", exit_time)
        for name in ("entry_price", "exit_price"):
            normalized = _finite(getattr(self, name), name=name)
            if normalized <= 0:
                raise ValueError(f"{name} must be positive")
            object.__setattr__(self, name, normalized)
        for name in ("gross_pnl", "net_pnl", "cost_paid"):
            normalized = _finite(getattr(self, name), name=name)
            if name == "cost_paid" and normalized < 0:
                raise ValueError("cost_paid must be non-negative")
            object.__setattr__(self, name, normalized)
        if type(self.forced) is not bool:
            raise TypeError("forced must be a bool")


@dataclass(frozen=True, slots=True)
class EquityPoint:
    event_time: datetime
    session: date
    equity: float
    gross_exposure: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "event_time", _utc(self.event_time, name="event_time"))
        if type(self.session) is not date:
            raise TypeError("session must be an exact date")
        for name in ("equity", "gross_exposure"):
            normalized = _finite(getattr(self, name), name=name)
            if normalized < 0:
                raise ValueError(f"{name} must be non-negative")
            object.__setattr__(self, name, normalized)


def _session_returns(
    equity_curve: tuple[EquityPoint, ...],
    *,
    initial_cash: float,
) -> tuple[float, ...]:
    ending_equity: dict[date, float] = {}
    for point in sorted(equity_curve, key=lambda item: item.event_time):
        ending_equity[point.session] = point.equity
    returns: list[float] = []
    previous = initial_cash
    for session in sorted(ending_equity):
        current = ending_equity[session]
        returns.append(current / previous - 1.0 if previous > 0 else 0.0)
        previous = current
    return tuple(returns)


def _maximum_drawdown(
    equity_curve: tuple[EquityPoint, ...],
    *,
    initial_cash: float,
) -> float:
    peak = initial_cash
    maximum = 0.0
    for point in sorted(equity_curve, key=lambda item: item.event_time):
        peak = max(peak, point.equity)
        if peak > 0:
            maximum = max(maximum, 1.0 - point.equity / peak)
    return maximum


def compute_metrics(
    trades: tuple[TradeRecord, ...],
    equity_curve: tuple[EquityPoint, ...],
    *,
    initial_cash: float,
) -> dict[str, float]:
    """Compute finite descriptive metrics.

    Volatility and Sharpe use close-to-close XNYS session returns, a zero
    risk-free rate, sample standard deviation, and ``sqrt(252)``
    annualization.  With fewer than two sessions, both values are zero.
    """
    initial_cash = _finite(initial_cash, name="initial_cash")
    if initial_cash <= 0:
        raise ValueError("initial_cash must be positive")

    ordered_trades = tuple(
        sorted(
            trades,
            key=lambda trade: (
                trade.exit_time,
                trade.entry_time,
                trade.symbol,
            ),
        )
    )
    ordered_equity = tuple(sorted(equity_curve, key=lambda point: point.event_time))
    final_equity = ordered_equity[-1].equity if ordered_equity else initial_cash
    returns = _session_returns(ordered_equity, initial_cash=initial_cash)
    session_volatility = stdev(returns) if len(returns) >= 2 else 0.0
    annualized_volatility = session_volatility * sqrt(TRADING_SESSIONS_PER_YEAR)
    sharpe = (
        fmean(returns) / session_volatility * sqrt(TRADING_SESSIONS_PER_YEAR)
        if session_volatility > 0
        else 0.0
    )

    wins = [trade.net_pnl for trade in ordered_trades if trade.net_pnl > 0]
    losses = [-trade.net_pnl for trade in ordered_trades if trade.net_pnl < 0]
    trade_count = len(ordered_trades)
    profit_factor = sum(wins) / sum(losses) if losses else 0.0
    win_rate = len(wins) / trade_count if trade_count else 0.0
    expectancy = fmean(trade.net_pnl for trade in ordered_trades) if trade_count else 0.0
    exposure = (
        fmean(
            point.gross_exposure / point.equity if point.equity > 0 else 0.0
            for point in ordered_equity
        )
        if ordered_equity
        else 0.0
    )
    turnover_notional = sum(
        trade.quantity * (trade.entry_price + trade.exit_price) for trade in ordered_trades
    )
    metrics = {
        "annualized_volatility": annualized_volatility,
        "cost_paid": sum(trade.cost_paid for trade in ordered_trades),
        "expectancy": expectancy,
        "exposure": exposure,
        "max_drawdown": _maximum_drawdown(
            ordered_equity,
            initial_cash=initial_cash,
        ),
        "net_return": final_equity / initial_cash - 1.0,
        "profit_factor": profit_factor,
        "sharpe": sharpe,
        "trade_count": float(trade_count),
        "turnover": turnover_notional / initial_cash,
        "win_rate": win_rate,
    }
    for symbol in sorted({trade.symbol for trade in ordered_trades}):
        metrics[f"pnl_by_symbol:{symbol}"] = sum(
            trade.net_pnl for trade in ordered_trades if trade.symbol == symbol
        )
    for session in sorted({trade.session for trade in ordered_trades}):
        metrics[f"pnl_by_session:{session.isoformat()}"] = sum(
            trade.net_pnl for trade in ordered_trades if trade.session == session
        )
    return dict(sorted(metrics.items()))
