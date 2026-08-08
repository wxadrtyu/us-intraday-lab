from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import cast


def _returns(value: object, *, name: str) -> tuple[float, ...]:
    if type(value) is not tuple:
        raise TypeError(f"{name} must be an exact tuple")
    normalized: list[float] = []
    for item in value:
        if type(item) not in {int, float}:
            raise TypeError(f"{name} must contain exact finite numbers")
        number = float(cast("int | float", item))
        if not math.isfinite(number) or number <= -1.0:
            raise ValueError(f"{name} must contain finite returns greater than -1")
        normalized.append(number)
    return tuple(normalized)


def _total_return(returns: tuple[float, ...]) -> float:
    return math.prod(1.0 + value for value in returns) - 1.0


@dataclass(frozen=True, slots=True)
class LongHorizonOosMetrics:
    oos_sessions: int
    strategy_total_return: float
    benchmark_total_return: float
    excess_total_return: float
    cost_1_5x_total_return: float
    cost_1_5x_annualized_return: float
    information_ratio: float
    tracking_error: float

    def __post_init__(self) -> None:
        if type(self.oos_sessions) is not int or self.oos_sessions < 2:
            raise ValueError("oos_sessions must be at least two")
        for field in (
            "strategy_total_return",
            "benchmark_total_return",
            "excess_total_return",
            "cost_1_5x_total_return",
            "cost_1_5x_annualized_return",
            "information_ratio",
            "tracking_error",
        ):
            value = getattr(self, field)
            if type(value) is not float or not math.isfinite(value):
                raise ValueError(f"{field} must be a finite float")
        if self.tracking_error <= 0.0:
            raise ValueError("tracking_error must be positive")


def compute_long_horizon_oos_metrics(
    *,
    strategy_session_returns: tuple[float, ...],
    benchmark_session_returns: tuple[float, ...],
    cost_1_5x_session_returns: tuple[float, ...],
    annualization_sessions: int = 252,
) -> LongHorizonOosMetrics:
    """Compute geometric OOS return and annualized IR against QQQ."""

    strategy = _returns(strategy_session_returns, name="strategy_session_returns")
    benchmark = _returns(benchmark_session_returns, name="benchmark_session_returns")
    stressed = _returns(cost_1_5x_session_returns, name="cost_1_5x_session_returns")
    if len(strategy) != len(benchmark) or len(strategy) != len(stressed):
        raise ValueError("OOS return tuples must have equal lengths")
    if len(strategy) < 2:
        raise ValueError("OOS metrics require at least two sessions")
    if type(annualization_sessions) is not int or annualization_sessions <= 0:
        raise ValueError("annualization_sessions must be a positive integer")
    active = tuple(
        strategy_return - benchmark_return
        for strategy_return, benchmark_return in zip(strategy, benchmark, strict=True)
    )
    active_stdev = statistics.stdev(active)
    if active_stdev <= 0.0:
        raise ValueError("OOS_INFORMATION_RATIO_UNDEFINED")
    tracking_error = active_stdev * math.sqrt(annualization_sessions)
    information_ratio = (
        statistics.fmean(active) * annualization_sessions / tracking_error
    )
    strategy_total = _total_return(strategy)
    benchmark_total = _total_return(benchmark)
    stressed_total = _total_return(stressed)
    stressed_annualized = (1.0 + stressed_total) ** (
        annualization_sessions / len(stressed)
    ) - 1.0
    return LongHorizonOosMetrics(
        oos_sessions=len(strategy),
        strategy_total_return=float(strategy_total),
        benchmark_total_return=float(benchmark_total),
        excess_total_return=float(strategy_total - benchmark_total),
        cost_1_5x_total_return=float(stressed_total),
        cost_1_5x_annualized_return=float(stressed_annualized),
        information_ratio=float(information_ratio),
        tracking_error=float(tracking_error),
    )
