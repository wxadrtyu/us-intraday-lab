"""Exact-minute evaluator for the frozen long-only take-profit ensemble."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

import duckdb
import numpy as np
import pandas as pd

from us_intraday_lab.portfolio_research import annual_drawdown_profit_factor


@dataclass(frozen=True, slots=True)
class TpEnsembleParameters:
    stock_excess_floor: float
    stock_range_floor: float
    fallback_exit_minute: Literal[300, 330]

    def __post_init__(self) -> None:
        if self.stock_excess_floor not in {0.005, 0.0075, 0.01}:
            raise ValueError("stock excess floor is outside the frozen neighborhood")
        if self.stock_range_floor not in {0.6, 0.65}:
            raise ValueError("stock range floor is outside the frozen neighborhood")
        if self.fallback_exit_minute not in {300, 330}:
            raise ValueError("fallback exit is outside the frozen neighborhood")


@dataclass(frozen=True, slots=True)
class TpEnsembleEvaluation:
    sessions: tuple[object, ...]
    session_returns: tuple[float, ...]
    benchmark_returns: tuple[float, ...]
    components: pd.DataFrame
    action: pd.Series
    opportunity_symbol: pd.Series
    stock_opportunity_return: pd.Series
    stock_opportunity_benchmark: pd.Series
    fallback_eligible: pd.Series
    fallback_return: pd.Series
    fallback_benchmark: pd.Series
    round_trip_cost: float
    trade_count: int


def _wide(
    frame: pd.DataFrame, dates: pd.Index, symbols: tuple[str, ...], column: str
) -> pd.DataFrame:
    return frame.pivot(index="session_date", columns="symbol", values=column).reindex(
        index=dates, columns=symbols
    )


def _stock_minute_outcomes(
    opportunities: pd.DataFrame,
    raw_paths: tuple[Path, ...],
    *,
    round_trip_cost: float,
) -> tuple[pd.Series, pd.Series]:
    if opportunities.empty:
        empty = pd.Series(dtype=float, index=pd.Index([], name="session_date"))
        return empty, empty.copy()
    bar_frames = []
    for raw_path in raw_paths:
        connection = duckdb.connect()
        connection.register(
            "opportunities", opportunities[["opportunity_id", "session_date", "symbol"]]
        )
        bar_frames.append(
            connection.execute(
                """
                WITH source AS (
                    SELECT timezone('America/New_York', datetime) AS timestamp,
                           symbol, high, spy_logret_1,
                           (date_part('hour', timezone('America/New_York', datetime)) - 9) * 60
                             + date_part('minute', timezone('America/New_York', datetime)) - 30
                               AS minute_index
                    FROM read_parquet(?)
                )
                SELECT opportunities.opportunity_id, source.minute_index,
                       source.high, source.spy_logret_1
                FROM opportunities
                JOIN source ON source.symbol = opportunities.symbol
                  AND CAST(source.timestamp AS DATE) = opportunities.session_date
                WHERE source.minute_index >= 46 AND source.minute_index < 330
                ORDER BY opportunities.opportunity_id, source.minute_index
                """,
                [raw_path.resolve().as_posix()],
            ).fetch_df()
        )
        connection.close()
    bars = pd.concat(bar_frames, ignore_index=True)
    grouped = {
        int(cast(Any, key)): value for key, value in bars.groupby("opportunity_id", sort=True)
    }
    stock_returns: dict[object, float] = {}
    benchmark_returns: dict[object, float] = {}
    for raw_record in opportunities.to_dict(orient="records"):
        record = cast(dict[str, Any], raw_record)
        trade_bars = grouped.get(int(record["opportunity_id"]))
        if trade_bars is None or trade_bars["minute_index"].nunique() < 280:
            continue
        hits = trade_bars.loc[trade_bars["high"] >= float(record["entry"]) * 1.02]
        if len(hits):
            used = trade_bars.loc[: cast(Any, hits.index[0])]
            raw_return = 0.02
        else:
            used = trade_bars
            raw_return = float(record["exit_330"]) / float(record["entry"]) - 1.0
        stock_returns[record["session_date"]] = raw_return - round_trip_cost
        benchmark_returns[record["session_date"]] = math.expm1(float(used["spy_logret_1"].sum()))
    return pd.Series(stock_returns, dtype=float), pd.Series(benchmark_returns, dtype=float)


def _fallback_minute_returns(raw_paths: tuple[Path, ...]) -> dict[int, pd.Series]:
    frames = []
    for raw_path in raw_paths:
        connection = duckdb.connect()
        frames.append(
            connection.execute(
                """
                WITH localized AS (
                    SELECT timezone('America/New_York', datetime) AS timestamp,
                           spy_logret_1
                    FROM read_parquet(?)
                ), unique_minutes AS (
                    SELECT CAST(timestamp AS DATE) AS session_date, timestamp,
                           (date_part('hour', timestamp) - 9) * 60
                             + date_part('minute', timestamp) - 30 AS minute_index,
                           avg(spy_logret_1) AS spy_logret_1
                    FROM localized
                    WHERE CAST(timestamp AS TIME) >= TIME '09:30:00'
                      AND CAST(timestamp AS TIME) < TIME '16:00:00'
                    GROUP BY session_date, timestamp
                )
                SELECT session_date,
                       exp(sum(spy_logret_1) FILTER (
                           WHERE minute_index >= 46 AND minute_index < 300
                       )) - 1.0 AS return_300,
                       exp(sum(spy_logret_1) FILTER (
                           WHERE minute_index >= 46 AND minute_index < 330
                       )) - 1.0 AS return_330
                FROM unique_minutes
                GROUP BY session_date
                ORDER BY session_date
                """,
                [raw_path.resolve().as_posix()],
            ).fetch_df()
        )
        connection.close()
    frame = pd.concat(frames, ignore_index=True)
    if frame["session_date"].duplicated().any():
        raise ValueError("raw paths overlap in fallback session coverage")
    return {
        minute: frame.set_index("session_date")[f"return_{minute}"].astype(float)
        for minute in (300, 330)
    }


def spy_interval_returns(
    raw_paths: tuple[Path, ...],
    *,
    entry_minute: int,
    exit_minutes: tuple[int, ...],
) -> dict[int, pd.Series]:
    """Return exact SPY returns from an entry open to each scheduled exit open."""

    if not raw_paths:
        raise ValueError("at least one raw path is required")
    if not 0 <= entry_minute < 389:
        raise ValueError("entry minute is outside regular trading hours")
    if (
        not exit_minutes
        or tuple(sorted(set(exit_minutes))) != exit_minutes
        or any(minute <= entry_minute or minute > 389 for minute in exit_minutes)
    ):
        raise ValueError("exit minutes must be sorted, unique, and after entry")
    select_values = ",\n".join(
        f"exp(sum(spy_logret_1) FILTER (WHERE minute_index >= {entry_minute} "
        f"AND minute_index < {minute})) - 1.0 AS return_{minute}"
        for minute in exit_minutes
    )
    frames = []
    for raw_path in raw_paths:
        connection = duckdb.connect()
        frames.append(
            connection.execute(
                f"""
                WITH localized AS (
                    SELECT timezone('America/New_York', datetime) AS timestamp,
                           spy_logret_1
                    FROM read_parquet(?)
                ), unique_minutes AS (
                    SELECT CAST(timestamp AS DATE) AS session_date, timestamp,
                           (date_part('hour', timestamp) - 9) * 60
                             + date_part('minute', timestamp) - 30 AS minute_index,
                           avg(spy_logret_1) AS spy_logret_1
                    FROM localized
                    WHERE CAST(timestamp AS TIME) >= TIME '09:30:00'
                      AND CAST(timestamp AS TIME) < TIME '16:00:00'
                    GROUP BY session_date, timestamp
                )
                SELECT session_date, {select_values}
                FROM unique_minutes
                GROUP BY session_date
                ORDER BY session_date
                """,
                [raw_path.resolve().as_posix()],
            ).fetch_df()
        )
        connection.close()
    frame = pd.concat(frames, ignore_index=True)
    if frame["session_date"].duplicated().any():
        raise ValueError("raw paths overlap in SPY interval session coverage")
    return {
        minute: frame.set_index("session_date")[f"return_{minute}"].astype(float)
        for minute in exit_minutes
    }


def _compose(
    dates: pd.Index,
    symbols: tuple[str, ...],
    action: pd.Series,
    opportunity_symbol: pd.Series,
    stock_return: pd.Series,
    stock_benchmark: pd.Series,
    fallback_eligible: pd.Series,
    fallback_return: pd.Series,
    fallback_benchmark: pd.Series,
    *,
    round_trip_cost: float,
) -> TpEnsembleEvaluation:
    action = action.reindex(dates).fillna("NONE").astype(str)
    returns = pd.Series(0.0, index=dates)
    benchmark = pd.Series(0.0, index=dates)
    components = pd.DataFrame(0.0, index=dates, columns=(*symbols, "SPY"))
    stock_mask = action == "STOCK"
    fallback_mask = action == "SPY"
    returns.loc[stock_mask] = stock_return.reindex(dates).loc[stock_mask]
    benchmark.loc[stock_mask] = stock_benchmark.reindex(dates).loc[stock_mask]
    for session in dates[stock_mask]:
        symbol = str(opportunity_symbol.loc[session])
        components.loc[session, symbol] = returns.loc[session]
    returns.loc[fallback_mask] = fallback_return.reindex(dates).loc[fallback_mask]
    benchmark.loc[fallback_mask] = fallback_benchmark.reindex(dates).loc[fallback_mask]
    components.loc[fallback_mask, "SPY"] = returns.loc[fallback_mask]
    return TpEnsembleEvaluation(
        sessions=tuple(dates),
        session_returns=tuple(float(value) for value in returns),
        benchmark_returns=tuple(float(value) for value in benchmark),
        components=components,
        action=action,
        opportunity_symbol=opportunity_symbol.reindex(dates),
        stock_opportunity_return=stock_return.reindex(dates),
        stock_opportunity_benchmark=stock_benchmark.reindex(dates),
        fallback_eligible=fallback_eligible.reindex(dates).fillna(False).astype(bool),
        fallback_return=fallback_return.reindex(dates),
        fallback_benchmark=fallback_benchmark.reindex(dates),
        round_trip_cost=round_trip_cost,
        trade_count=int(stock_mask.sum() + fallback_mask.sum()),
    )


def evaluate_tp_ensemble(
    frame: pd.DataFrame,
    benchmark_rth: pd.Series,
    raw_paths: tuple[Path, ...],
    parameters: TpEnsembleParameters,
    *,
    universe: tuple[str, ...],
    round_trip_cost: float,
    expected_universe_size: int = 51,
) -> TpEnsembleEvaluation:
    """Evaluate the frozen strategy using only causal features and exact minute exits."""

    if expected_universe_size not in {50, 51}:
        raise ValueError("expected universe size must be 50 or 51")
    if tuple(sorted(set(universe))) != universe or len(universe) != expected_universe_size:
        raise ValueError(f"universe must contain {expected_universe_size} sorted unique symbols")
    if not 0.0 <= round_trip_cost < 0.01:
        raise ValueError("round-trip cost is invalid")
    frame = frame.loc[frame["symbol"].isin(universe)].copy()
    dates = pd.Index(sorted(frame["session_date"].unique()), name="session_date")
    if len(dates) < 20:
        raise ValueError("v3 evaluation requires at least twenty sessions")
    day_open = _wide(frame, dates, universe, "day_open")
    close = _wide(frame, dates, universe, "close_45")
    entry = _wide(frame, dates, universe, "open_46")
    exit_330 = _wide(frame, dates, universe, "open_330")
    volume = _wide(frame, dates, universe, "cum_volume_45")
    vwap = _wide(frame, dates, universe, "vwap_45")
    high = _wide(frame, dates, universe, "range_high_45")
    low = _wide(frame, dates, universe, "range_low_45")
    spy = {
        minute: _wide(frame, dates, universe, f"spy_current_{minute}").median(axis=1)
        for minute in (45, 300, 330)
    }
    current = close / day_open - 1.0
    excess = current.sub(spy[45], axis=0)
    relative_volume = volume / volume.shift(1).rolling(20, min_periods=10).median()
    range_position = (close - low) / (high - low)
    ranks = current.rank(axis=1, ascending=False, method="first")
    top = ranks == 1
    opportunity_symbol = top.idxmax(axis=1).where(top.any(axis=1))
    opportunity_rows = []
    for opportunity_id, session in enumerate(dates):
        symbol = opportunity_symbol.loc[session]
        if pd.isna(symbol):
            continue
        entry_price = entry.loc[session, symbol]
        exit_price = exit_330.loc[session, symbol]
        if pd.isna(entry_price) or pd.isna(exit_price):
            continue
        opportunity_rows.append(
            {
                "opportunity_id": opportunity_id,
                "session_date": session,
                "symbol": str(symbol),
                "entry": float(entry_price),
                "exit_330": float(exit_price),
            }
        )
    opportunities = pd.DataFrame(opportunity_rows)
    stock_return, stock_benchmark = _stock_minute_outcomes(
        opportunities, raw_paths, round_trip_cost=round_trip_cost
    )
    fallback_outcomes = _fallback_minute_returns(raw_paths)
    selected = (
        top
        & (current >= 0.003)
        & (excess >= parameters.stock_excess_floor)
        & (relative_volume >= 1.5)
        & (close >= vwap)
        & (range_position >= parameters.stock_range_floor)
        & (spy[45] >= 0.0).to_numpy()[:, None]
        & (spy[45] <= 0.01).to_numpy()[:, None]
    ).any(axis=1)
    selected &= stock_return.reindex(dates).notna()
    benchmark_rth = benchmark_rth.reindex(dates).fillna(0.0)
    fallback_eligible = (
        benchmark_rth.shift(1).gt(0.0) & spy[45].ge(0.002) & spy[45].le(0.025) & ~selected
    )
    fallback_benchmark = fallback_outcomes[parameters.fallback_exit_minute].reindex(dates)
    fallback_return = fallback_benchmark - round_trip_cost
    action = pd.Series("NONE", index=dates)
    action.loc[selected] = "STOCK"
    action.loc[fallback_eligible] = "SPY"
    return _compose(
        dates,
        universe,
        action,
        opportunity_symbol,
        stock_return,
        stock_benchmark,
        fallback_eligible,
        fallback_return,
        fallback_benchmark,
        round_trip_cost=round_trip_cost,
    )


def slice_tp_evaluation(
    evaluation: TpEnsembleEvaluation, sessions: tuple[object, ...]
) -> TpEnsembleEvaluation:
    dates = pd.Index(sessions, name="session_date")
    if not dates.isin(evaluation.sessions).all():
        raise ValueError("requested sessions are outside the evaluation")
    symbols = tuple(str(value) for value in evaluation.components.columns if value != "SPY")
    return _compose(
        dates,
        symbols,
        evaluation.action,
        evaluation.opportunity_symbol,
        evaluation.stock_opportunity_return,
        evaluation.stock_opportunity_benchmark,
        evaluation.fallback_eligible,
        evaluation.fallback_return,
        evaluation.fallback_benchmark,
        round_trip_cost=evaluation.round_trip_cost,
    )


def exclude_tp_symbol(evaluation: TpEnsembleEvaluation, symbol: str) -> TpEnsembleEvaluation:
    if symbol not in evaluation.components.columns or symbol == "SPY":
        raise ValueError("excluded symbol is outside the stock universe")
    action = evaluation.action.copy()
    removed = (action == "STOCK") & evaluation.opportunity_symbol.eq(symbol)
    action.loc[removed] = "NONE"
    action.loc[removed & evaluation.fallback_eligible] = "SPY"
    symbols = tuple(str(value) for value in evaluation.components.columns if value != "SPY")
    return _compose(
        pd.Index(evaluation.sessions, name="session_date"),
        symbols,
        action,
        evaluation.opportunity_symbol,
        evaluation.stock_opportunity_return,
        evaluation.stock_opportunity_benchmark,
        evaluation.fallback_eligible,
        evaluation.fallback_return,
        evaluation.fallback_benchmark,
        round_trip_cost=evaluation.round_trip_cost,
    )


def tp_null_distributions(
    evaluation: TpEnsembleEvaluation, *, repetitions: int, seed: int
) -> dict[str, tuple[float, ...]]:
    """Reassign action types to daily opportunities while preserving action counts."""

    if repetitions < 100 or len(evaluation.sessions) < 10:
        raise ValueError("null-test scope is too small")
    dates = pd.Index(evaluation.sessions, name="session_date")
    original = list(evaluation.action)
    rng = random.Random(seed)

    def score(actions: list[str]) -> float:
        action = pd.Series(actions, index=dates)
        valid_stock = evaluation.stock_opportunity_return.notna()
        action.loc[(action == "STOCK") & ~valid_stock] = "NONE"
        valid_fallback = evaluation.fallback_return.notna()
        action.loc[(action == "SPY") & ~valid_fallback] = "NONE"
        symbols = tuple(str(value) for value in evaluation.components.columns if value != "SPY")
        recomposed = _compose(
            dates,
            symbols,
            action,
            evaluation.opportunity_symbol,
            evaluation.stock_opportunity_return,
            evaluation.stock_opportunity_benchmark,
            evaluation.fallback_eligible,
            evaluation.fallback_return,
            evaluation.fallback_benchmark,
            round_trip_cost=evaluation.round_trip_cost,
        )
        return math.prod(1.0 + value for value in recomposed.session_returns) - 1.0

    permutation: list[float] = []
    circular: list[float] = []
    for _ in range(repetitions):
        shuffled = original.copy()
        rng.shuffle(shuffled)
        permutation.append(score(shuffled))
        shift = rng.randrange(1, len(original))
        circular.append(score(original[-shift:] + original[:-shift]))
    return {
        "SESSION_SIGNAL_PERMUTATION": tuple(permutation),
        "SESSION_CIRCULAR_SHIFT": tuple(circular),
    }


def tp_metrics(evaluation: TpEnsembleEvaluation, *, fold_count: int) -> dict[str, object]:
    returns = pd.Series(evaluation.session_returns, index=evaluation.sessions, dtype=float)
    benchmark = pd.Series(evaluation.benchmark_returns, index=evaluation.sessions, dtype=float)
    annual, drawdown, profit_factor = annual_drawdown_profit_factor(returns)
    positive = evaluation.components.sum().clip(lower=0.0)
    concentration = float(positive.max() / positive.sum()) if float(positive.sum()) > 0 else 1.0
    boundaries = np.linspace(0, len(returns), fold_count + 1, dtype=int)
    folds = tuple(
        annual_drawdown_profit_factor(returns.iloc[boundaries[index] : boundaries[index + 1]])[0]
        for index in range(fold_count)
    )
    active = returns - benchmark
    deviation = float(active.std(ddof=1))
    information_ratio = (
        float(active.mean() / deviation * math.sqrt(252.0)) if deviation else -math.inf
    )
    return {
        "sessions": len(returns),
        "start": str(returns.index.min()),
        "end": str(returns.index.max()),
        "total_return": float(cast(Any, (1.0 + returns.astype(float)).prod())) - 1.0,
        "annualized_return": annual,
        "information_ratio": information_ratio,
        "max_drawdown": drawdown,
        "profit_factor": profit_factor,
        "trades": evaluation.trade_count,
        "positive_symbol_concentration": concentration,
        "folds": folds,
        "pnl_by_symbol": {
            str(symbol): float(value) for symbol, value in evaluation.components.sum().items()
        },
    }


def validate_period_sessions(
    sessions: tuple[object, ...],
    *,
    start: str,
    end_exclusive: str,
    minimum_sessions: int,
) -> tuple[pd.Timestamp, ...]:
    """Normalize date-like values and fail closed when a sealed period drifts."""

    normalized = tuple(pd.Timestamp(cast(Any, value)).normalize() for value in sessions)
    if (
        len(normalized) < minimum_sessions
        or tuple(sorted(set(normalized))) != normalized
        or min(normalized) < pd.Timestamp(start)
        or max(normalized) >= pd.Timestamp(end_exclusive)
    ):
        raise ValueError("sealed period sessions are outside the frozen scope")
    return normalized
