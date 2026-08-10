"""Causal evaluation core for the frozen long-only cross-sectional portfolio."""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class PortfolioEvaluation:
    sessions: tuple[object, ...]
    session_returns: tuple[float, ...]
    benchmark_returns: tuple[float, ...]
    components: pd.DataFrame
    strength_selected: pd.DataFrame
    recovery_selected: pd.DataFrame
    strength_raw_returns: pd.DataFrame
    recovery_raw_returns: pd.DataFrame
    strength_spy_returns: pd.Series
    recovery_spy_returns: pd.Series
    overlap_strength_share: float
    round_trip_cost: float
    trade_count: int


def annual_drawdown_profit_factor(returns: pd.Series) -> tuple[float, float, float]:
    values = returns.astype(float).fillna(0.0)
    if len(values) < 2:
        raise ValueError("portfolio metrics require at least two sessions")
    equity = (1.0 + values).cumprod()
    annual = float(equity.iloc[-1] ** (252.0 / len(values)) - 1.0)
    drawdown = abs(float((equity / equity.cummax() - 1.0).min()))
    gains = float(values.clip(lower=0.0).sum())
    losses = abs(float(values.clip(upper=0.0).sum()))
    return annual, drawdown, gains / losses if losses else math.inf


def information_ratio(returns: pd.Series, benchmark: pd.Series) -> float:
    active = returns.astype(float) - benchmark.astype(float)
    deviation = float(active.std(ddof=1))
    return float(active.mean() / deviation * math.sqrt(252.0)) if deviation else -math.inf


def _wide(
    frame: pd.DataFrame, dates: pd.Index, symbols: tuple[str, ...], column: str
) -> pd.DataFrame:
    return frame.pivot(index="session_date", columns="symbol", values=column).reindex(
        index=dates, columns=symbols
    )


def _compose(
    strength_selected: pd.DataFrame,
    recovery_selected: pd.DataFrame,
    strength_raw: pd.DataFrame,
    recovery_raw: pd.DataFrame,
    strength_spy: pd.Series,
    recovery_spy: pd.Series,
    *,
    overlap_strength_share: float,
    round_trip_cost: float,
) -> PortfolioEvaluation:
    strength_counts = strength_selected.sum(axis=1).replace(0, np.nan)
    recovery_counts = recovery_selected.sum(axis=1).replace(0, np.nan)
    strength_positions = strength_selected.div(strength_counts, axis=0).fillna(0.0)
    recovery_positions = recovery_selected.div(recovery_counts, axis=0).fillna(0.0)
    strength_active = strength_positions.sum(axis=1) > 0.0
    recovery_active = recovery_positions.sum(axis=1) > 0.0
    both = strength_active & recovery_active
    strength_weight = strength_active.astype(float)
    recovery_weight = recovery_active.astype(float)
    strength_weight.loc[both] = overlap_strength_share
    recovery_weight.loc[both] = 1.0 - overlap_strength_share
    strength_components = strength_positions * (strength_raw - round_trip_cost)
    recovery_components = recovery_positions * (recovery_raw - round_trip_cost)
    components = strength_components.mul(strength_weight, axis=0) + recovery_components.mul(
        recovery_weight, axis=0
    )
    returns = components.sum(axis=1).fillna(0.0)
    benchmark = (strength_spy * strength_weight + recovery_spy * recovery_weight).fillna(0.0)
    return PortfolioEvaluation(
        sessions=tuple(returns.index),
        session_returns=tuple(float(value) for value in returns),
        benchmark_returns=tuple(float(value) for value in benchmark),
        components=components,
        strength_selected=strength_selected,
        recovery_selected=recovery_selected,
        strength_raw_returns=strength_raw,
        recovery_raw_returns=recovery_raw,
        strength_spy_returns=strength_spy,
        recovery_spy_returns=recovery_spy,
        overlap_strength_share=overlap_strength_share,
        round_trip_cost=round_trip_cost,
        trade_count=int(strength_selected.sum().sum() + recovery_selected.sum().sum()),
    )


def evaluate_frozen_portfolio(
    frame: pd.DataFrame,
    parameters: list[Any],
    *,
    round_trip_cost: float,
) -> PortfolioEvaluation:
    """Evaluate the exact two-branch frozen portfolio on chronologically joined features."""

    if len(parameters) != 3:
        raise ValueError("frozen portfolio parameters must contain two branches and a share")
    strength, recovery, overlap_share = parameters
    if len(strength) != 6 or len(recovery) != 5 or float(overlap_share) not in {0.25, 0.5}:
        raise ValueError("frozen portfolio parameter shape is invalid")
    strength_decision, strength_exit, strength_count, volume_floor, strength_floor, excess_floor = (
        strength
    )
    recovery_decision, recovery_exit, recovery_count, recovery_regime, bounce = recovery
    if (
        int(strength_decision) != 45
        or int(strength_exit) not in {300, 330, 360}
        or int(strength_count) != 3
        or float(volume_floor) != 1.5
        or float(strength_floor) != 0.005
        or float(excess_floor) != 0.02
        or int(recovery_decision) != 60
        or int(recovery_exit) != 360
        or int(recovery_count) not in {3, 5}
        or recovery_regime != "spy_down"
        or float(bounce) != 0.003
    ):
        raise ValueError("parameters fall outside the frozen proposal")
    if not 0.0 <= round_trip_cost < 0.01:
        raise ValueError("round_trip_cost is invalid")
    dates = pd.Index(sorted(frame["session_date"].unique()), name="session_date")
    symbols = tuple(sorted(frame["symbol"].unique()))
    day_open = _wide(frame, dates, symbols, "day_open")
    day_close = _wide(frame, dates, symbols, "day_close")
    trail3 = day_close.pct_change(3, fill_method=None).shift(1)
    close_30 = _wide(frame, dates, symbols, "close_30")
    close_45 = _wide(frame, dates, symbols, "close_45")
    close_60 = _wide(frame, dates, symbols, "close_60")
    open_46 = _wide(frame, dates, symbols, "open_46")
    open_61 = _wide(frame, dates, symbols, "open_61")
    open_strength_exit = _wide(frame, dates, symbols, f"open_{int(strength_exit)}")
    open_recovery_exit = _wide(frame, dates, symbols, "open_360")
    vwap_45 = _wide(frame, dates, symbols, "vwap_45")
    volume_45 = _wide(frame, dates, symbols, "cum_volume_45")
    high_45 = _wide(frame, dates, symbols, "range_high_45")
    low_45 = _wide(frame, dates, symbols, "range_low_45")
    spy = {
        minute: _wide(frame, dates, symbols, f"spy_current_{minute}").median(axis=1)
        for minute in {45, 60, int(strength_exit), 360}
    }
    strength_current = close_45 / day_open - 1.0
    relative_volume = volume_45 / volume_45.shift(1).rolling(20, min_periods=10).median()
    range_position = (close_45 - low_45) / (high_45 - low_45)
    top_strength = strength_current.rank(axis=1, ascending=False, method="first") <= int(
        strength_count
    )
    strength_selected = (
        top_strength
        & (strength_current >= float(strength_floor))
        & (strength_current.sub(spy[45], axis=0) >= float(excess_floor))
        & (relative_volume >= float(volume_floor))
        & (close_45 >= vwap_45)
        & (range_position >= 0.80)
        & (spy[45] > 0.0).to_numpy()[:, None]
    ).fillna(False)
    recovery_current = close_60 / day_open - 1.0
    recovery_recent = close_60 / close_30 - 1.0
    bottom_recovery = recovery_current.rank(axis=1, ascending=True, method="first") <= int(
        recovery_count
    )
    recovery_selected = (
        bottom_recovery
        & (recovery_current < 0.0)
        & (recovery_recent >= float(bounce))
        & (trail3 > -0.15)
        & (spy[60] <= 0.0).to_numpy()[:, None]
    ).fillna(False)
    strength_raw = open_strength_exit / open_46 - 1.0
    recovery_raw = open_recovery_exit / open_61 - 1.0
    strength_spy = (1.0 + spy[int(strength_exit)]) / (1.0 + spy[45]) - 1.0
    recovery_spy = (1.0 + spy[360]) / (1.0 + spy[60]) - 1.0
    return _compose(
        strength_selected,
        recovery_selected,
        strength_raw,
        recovery_raw,
        strength_spy,
        recovery_spy,
        overlap_strength_share=float(overlap_share),
        round_trip_cost=round_trip_cost,
    )


def slice_evaluation(
    evaluation: PortfolioEvaluation, sessions: tuple[object, ...]
) -> PortfolioEvaluation:
    index = pd.Index(evaluation.sessions)
    wanted = index.isin(sessions)
    selected_index = index[wanted]
    if tuple(selected_index) != sessions:
        raise ValueError("requested portfolio sessions are not exactly covered")
    return _compose(
        evaluation.strength_selected.loc[selected_index],
        evaluation.recovery_selected.loc[selected_index],
        evaluation.strength_raw_returns.loc[selected_index],
        evaluation.recovery_raw_returns.loc[selected_index],
        evaluation.strength_spy_returns.loc[selected_index],
        evaluation.recovery_spy_returns.loc[selected_index],
        overlap_strength_share=evaluation.overlap_strength_share,
        round_trip_cost=evaluation.round_trip_cost,
    )


def exclude_symbol(
    evaluation: PortfolioEvaluation,
    symbol: str,
    *,
    round_trip_cost: float,
) -> PortfolioEvaluation:
    if symbol not in evaluation.components.columns:
        raise ValueError("excluded symbol is outside the portfolio universe")
    strength = evaluation.strength_selected.copy()
    recovery = evaluation.recovery_selected.copy()
    strength[symbol] = False
    recovery[symbol] = False
    return _compose(
        strength,
        recovery,
        evaluation.strength_raw_returns,
        evaluation.recovery_raw_returns,
        evaluation.strength_spy_returns,
        evaluation.recovery_spy_returns,
        overlap_strength_share=evaluation.overlap_strength_share,
        round_trip_cost=round_trip_cost,
    )


def null_distributions(
    evaluation: PortfolioEvaluation,
    *,
    repetitions: int,
    seed: int,
    round_trip_cost: float,
) -> dict[str, tuple[float, ...]]:
    """Reassign frozen signals to sessions while preserving signal breadth and symbols."""

    if repetitions < 100:
        raise ValueError("null repetitions must be at least one hundred")
    size = len(evaluation.sessions)
    if size < 10:
        raise ValueError("null evaluation requires at least ten sessions")
    rng = random.Random(seed)
    permutation_scores: list[float] = []
    shift_scores: list[float] = []

    def score(order: list[int]) -> float:
        strength = evaluation.strength_selected.iloc[order].copy()
        recovery = evaluation.recovery_selected.iloc[order].copy()
        strength.index = evaluation.strength_selected.index
        recovery.index = evaluation.recovery_selected.index
        recomposed = _compose(
            strength,
            recovery,
            evaluation.strength_raw_returns,
            evaluation.recovery_raw_returns,
            evaluation.strength_spy_returns,
            evaluation.recovery_spy_returns,
            overlap_strength_share=evaluation.overlap_strength_share,
            round_trip_cost=round_trip_cost,
        )
        return math.prod(1.0 + value for value in recomposed.session_returns) - 1.0

    base = list(range(size))
    for _ in range(repetitions):
        order = base.copy()
        rng.shuffle(order)
        permutation_scores.append(score(order))
        shift = rng.randrange(1, size)
        shift_scores.append(score(base[-shift:] + base[:-shift]))
    return {
        "SESSION_SIGNAL_PERMUTATION": tuple(permutation_scores),
        "SESSION_CIRCULAR_SHIFT": tuple(shift_scores),
    }


def nearest_rank_percentile(values: tuple[float, ...], percentile: float) -> float:
    if not values or not 0.0 < percentile < 1.0:
        raise ValueError("invalid percentile evidence")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def tracking_statistics(evaluation: PortfolioEvaluation) -> tuple[float, float]:
    active = tuple(
        strategy - benchmark
        for strategy, benchmark in zip(
            evaluation.session_returns, evaluation.benchmark_returns, strict=True
        )
    )
    deviation = statistics.stdev(active)
    return statistics.fmean(active) / deviation * math.sqrt(252.0), deviation * math.sqrt(252.0)
