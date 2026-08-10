"""Exact-minute evaluator for the frozen long-only v4 dual-sleeve family."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from us_intraday_lab.portfolio_research import annual_drawdown_profit_factor
from us_intraday_lab.tp_ensemble import (
    TpEnsembleParameters,
    evaluate_tp_ensemble,
    spy_interval_returns,
)


@dataclass(frozen=True, slots=True)
class DualSleeveParameters:
    stock_excess_floor: float
    stock_range_floor: float
    spy_current_floor: float
    spy_exit_minute: Literal[240, 300, 330]

    def __post_init__(self) -> None:
        if self.stock_excess_floor not in {0.005, 0.0075}:
            raise ValueError("stock excess floor is outside the v4 neighborhood")
        if self.stock_range_floor not in {0.6, 0.65, 0.7}:
            raise ValueError("stock range floor is outside the v4 neighborhood")
        if self.spy_current_floor not in {0.002, 0.003}:
            raise ValueError("SPY current floor is outside the v4 neighborhood")
        if self.spy_exit_minute not in {240, 300, 330}:
            raise ValueError("SPY exit minute is outside the v4 neighborhood")


@dataclass(frozen=True, slots=True)
class DualSleevePrepared:
    dates: pd.Index
    symbols: tuple[str, ...]
    opportunity_symbol: pd.Series
    stock_return: pd.Series
    stock_benchmark: pd.Series
    stock_current: pd.DataFrame
    stock_excess: pd.DataFrame
    stock_relative_volume: pd.DataFrame
    stock_range_position: pd.DataFrame
    stock_above_vwap: pd.DataFrame
    stock_top: pd.DataFrame
    spy_current_30: pd.Series
    spy_current_45: pd.Series
    prior_spy_rth: pd.Series
    spy_returns: dict[int, pd.Series]
    round_trip_cost: float


@dataclass(frozen=True, slots=True)
class DualSleeveEvaluation:
    sessions: tuple[object, ...]
    session_returns: tuple[float, ...]
    benchmark_returns: tuple[float, ...]
    components: pd.DataFrame
    stock_active: pd.Series
    spy_active: pd.Series
    opportunity_symbol: pd.Series
    stock_return: pd.Series
    stock_benchmark: pd.Series
    spy_return: pd.Series
    round_trip_cost: float
    trade_count: int


def _wide(
    frame: pd.DataFrame, dates: pd.Index, symbols: tuple[str, ...], column: str
) -> pd.DataFrame:
    return frame.pivot(index="session_date", columns="symbol", values=column).reindex(
        index=dates, columns=symbols
    )


def prepare_dual_sleeve(
    frame: pd.DataFrame,
    benchmark_rth: pd.Series,
    raw_paths: tuple[Path, ...],
    *,
    universe: tuple[str, ...],
    round_trip_cost: float,
) -> DualSleevePrepared:
    """Prepare invariant v4 features and exact outcomes once for all 36 variants."""

    if tuple(sorted(set(universe))) != universe or len(universe) != 51:
        raise ValueError("v4 universe must contain 51 sorted unique symbols")
    if not 0.0 <= round_trip_cost < 0.01:
        raise ValueError("round-trip cost is invalid")
    frame = frame.loc[frame["symbol"].isin(universe)].copy()
    dates = pd.Index(sorted(frame["session_date"].unique()), name="session_date")
    if len(dates) < 20:
        raise ValueError("v4 preparation requires at least twenty sessions")
    base = evaluate_tp_ensemble(
        frame,
        benchmark_rth,
        raw_paths,
        TpEnsembleParameters(0.005, 0.6, 300),
        universe=universe,
        round_trip_cost=round_trip_cost,
    )
    day_open = _wide(frame, dates, universe, "day_open")
    close = _wide(frame, dates, universe, "close_45")
    volume = _wide(frame, dates, universe, "cum_volume_45")
    high = _wide(frame, dates, universe, "range_high_45")
    low = _wide(frame, dates, universe, "range_low_45")
    spy_current_30 = _wide(frame, dates, universe, "spy_current_30").median(axis=1)
    spy_current_45 = _wide(frame, dates, universe, "spy_current_45").median(axis=1)
    current = close / day_open - 1.0
    return DualSleevePrepared(
        dates=dates,
        symbols=universe,
        opportunity_symbol=base.opportunity_symbol,
        stock_return=base.stock_opportunity_return,
        stock_benchmark=base.stock_opportunity_benchmark,
        stock_current=current,
        stock_excess=current.sub(spy_current_45, axis=0),
        stock_relative_volume=volume / volume.shift(1).rolling(20, min_periods=10).median(),
        stock_range_position=(close - low) / (high - low),
        stock_above_vwap=close >= _wide(frame, dates, universe, "vwap_45"),
        stock_top=current.rank(axis=1, ascending=False, method="first") == 1,
        spy_current_30=spy_current_30,
        spy_current_45=spy_current_45,
        prior_spy_rth=benchmark_rth.reindex(dates).fillna(0.0).shift(1),
        spy_returns=spy_interval_returns(raw_paths, entry_minute=31, exit_minutes=(240, 300, 330)),
        round_trip_cost=round_trip_cost,
    )


def _compose(
    prepared: DualSleevePrepared,
    dates: pd.Index,
    stock_active: pd.Series,
    spy_active: pd.Series,
    spy_return: pd.Series,
) -> DualSleeveEvaluation:
    stock_active = stock_active.reindex(dates).fillna(False).astype(bool)
    spy_active = spy_active.reindex(dates).fillna(False).astype(bool)
    stock_return = prepared.stock_return.reindex(dates)
    stock_benchmark = prepared.stock_benchmark.reindex(dates)
    spy_return = spy_return.reindex(dates)
    returns = 0.5 * stock_return.fillna(0.0) * stock_active
    returns += 0.5 * (spy_return - prepared.round_trip_cost).fillna(0.0) * spy_active
    benchmark = 0.5 * stock_benchmark.fillna(0.0) * stock_active
    benchmark += 0.5 * spy_return.fillna(0.0) * spy_active
    components = pd.DataFrame(0.0, index=dates, columns=(*prepared.symbols, "SPY"))
    for session in dates[stock_active]:
        symbol = prepared.opportunity_symbol.loc[session]
        if pd.notna(symbol):
            components.loc[session, str(symbol)] = 0.5 * float(stock_return.loc[session])
    components.loc[spy_active, "SPY"] = 0.5 * (
        spy_return.loc[spy_active] - prepared.round_trip_cost
    )
    return DualSleeveEvaluation(
        sessions=tuple(dates),
        session_returns=tuple(float(value) for value in returns),
        benchmark_returns=tuple(float(value) for value in benchmark),
        components=components,
        stock_active=stock_active,
        spy_active=spy_active,
        opportunity_symbol=prepared.opportunity_symbol.reindex(dates),
        stock_return=stock_return,
        stock_benchmark=stock_benchmark,
        spy_return=spy_return,
        round_trip_cost=prepared.round_trip_cost,
        trade_count=int(stock_active.sum() + spy_active.sum()),
    )


def evaluate_dual_sleeve(
    prepared: DualSleevePrepared, parameters: DualSleeveParameters
) -> DualSleeveEvaluation:
    """Evaluate one frozen v4 variant from prepared causal inputs and outcomes."""

    stock_active = (
        prepared.stock_top
        & (prepared.stock_current >= 0.003)
        & (prepared.stock_excess >= parameters.stock_excess_floor)
        & (prepared.stock_relative_volume >= 1.5)
        & prepared.stock_above_vwap
        & (prepared.stock_range_position >= parameters.stock_range_floor)
        & prepared.spy_current_45.ge(0.0).to_numpy()[:, None]
        & prepared.spy_current_45.le(0.015).to_numpy()[:, None]
    ).any(axis=1)
    stock_active &= prepared.stock_return.reindex(prepared.dates).notna()
    spy_active = (
        prepared.spy_current_30.ge(parameters.spy_current_floor)
        & prepared.spy_current_30.le(0.04)
        & prepared.prior_spy_rth.gt(0.0)
    )
    return _compose(
        prepared,
        prepared.dates,
        stock_active,
        spy_active,
        prepared.spy_returns[parameters.spy_exit_minute],
    )


def slice_dual_sleeve(
    prepared: DualSleevePrepared,
    evaluation: DualSleeveEvaluation,
    sessions: tuple[object, ...],
) -> DualSleeveEvaluation:
    dates = pd.Index(sessions, name="session_date")
    if not dates.isin(evaluation.sessions).all():
        raise ValueError("requested sessions are outside the v4 evaluation")
    return _compose(
        prepared,
        dates,
        evaluation.stock_active,
        evaluation.spy_active,
        evaluation.spy_return,
    )


def exclude_dual_sleeve_symbol(
    prepared: DualSleevePrepared,
    evaluation: DualSleeveEvaluation,
    symbol: str,
) -> DualSleeveEvaluation:
    if symbol not in prepared.symbols:
        raise ValueError("excluded symbol is outside the v4 universe")
    stock_active = evaluation.stock_active & ~evaluation.opportunity_symbol.eq(symbol)
    return _compose(
        prepared,
        pd.Index(evaluation.sessions, name="session_date"),
        stock_active,
        evaluation.spy_active,
        evaluation.spy_return,
    )


def dual_sleeve_metrics(evaluation: DualSleeveEvaluation, *, fold_count: int) -> dict[str, object]:
    returns = pd.Series(evaluation.session_returns, index=evaluation.sessions, dtype=float)
    benchmark = pd.Series(evaluation.benchmark_returns, index=evaluation.sessions, dtype=float)
    annual, drawdown, profit_factor = annual_drawdown_profit_factor(returns)
    active = returns - benchmark
    deviation = float(active.std(ddof=1))
    information_ratio = (
        float(active.mean() / deviation * math.sqrt(252.0)) if deviation else -math.inf
    )
    positive = evaluation.components.sum().clip(lower=0.0)
    positive_sum = float(positive.to_numpy(dtype=float).sum())
    concentration = (
        float(positive.to_numpy(dtype=float).max() / positive_sum) if positive_sum else 1.0
    )
    boundaries = np.linspace(0, len(returns), fold_count + 1, dtype=int)
    folds = tuple(
        annual_drawdown_profit_factor(returns.iloc[boundaries[i] : boundaries[i + 1]])[0]
        for i in range(fold_count)
    )
    return {
        "sessions": len(returns),
        "total_return": math.prod(1.0 + float(value) for value in returns) - 1.0,
        "annualized_return": annual,
        "information_ratio": information_ratio,
        "max_drawdown": drawdown,
        "profit_factor": profit_factor,
        "trades": evaluation.trade_count,
        "positive_symbol_concentration": concentration,
        "folds": folds,
    }


def dual_sleeve_null_distributions(
    prepared: DualSleevePrepared,
    evaluation: DualSleeveEvaluation,
    *,
    repetitions: int,
    seed: int,
) -> dict[str, tuple[float, ...]]:
    """Reassign paired sleeve signals while preserving their joint session pattern."""

    if repetitions < 100 or len(evaluation.sessions) < 10:
        raise ValueError("v4 null-test scope is too small")
    dates = pd.Index(evaluation.sessions, name="session_date")
    stock = list(evaluation.stock_active.astype(bool))
    spy = list(evaluation.spy_active.astype(bool))
    rng = random.Random(seed)

    def score(stock_values: list[bool], spy_values: list[bool]) -> float:
        recomposed = _compose(
            prepared,
            dates,
            pd.Series(stock_values, index=dates),
            pd.Series(spy_values, index=dates),
            evaluation.spy_return,
        )
        return math.prod(1.0 + value for value in recomposed.session_returns) - 1.0

    permutation = []
    circular = []
    for _ in range(repetitions):
        order = list(range(len(stock)))
        rng.shuffle(order)
        permutation.append(score([stock[i] for i in order], [spy[i] for i in order]))
        shift = rng.randrange(1, len(stock))
        circular.append(score(stock[-shift:] + stock[:-shift], spy[-shift:] + spy[:-shift]))
    return {
        "SESSION_SIGNAL_PERMUTATION": tuple(permutation),
        "SESSION_CIRCULAR_SHIFT": tuple(circular),
    }
