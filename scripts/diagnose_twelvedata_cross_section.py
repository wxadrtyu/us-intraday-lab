"""Development-only scan of causal 37-stock cross-sectional intraday families."""

from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROUND_TRIP_COST_1_5X = 0.0009
MIN_COMPLETE_MINUTES = 385


@dataclass(frozen=True)
class Result:
    family: str
    parameters: tuple[object, ...]
    train_annual: float
    validation_annual: float
    validation_ir: float
    validation_drawdown: float
    validation_profit_factor: float
    validation_trades: int
    validation_concentration: float
    folds: tuple[float, ...]


def metrics(returns: pd.Series) -> tuple[float, float, float]:
    equity = (1.0 + returns).cumprod()
    annual = float(equity.iloc[-1] ** (252.0 / len(returns)) - 1.0)
    drawdown = float((equity / equity.cummax() - 1.0).min())
    gains = float(returns.clip(lower=0.0).sum())
    losses = abs(float(returns.clip(upper=0.0).sum()))
    return annual, drawdown, gains / losses if losses else math.inf


def information_ratio(returns: pd.Series, benchmark: pd.Series) -> float:
    active = returns - benchmark
    deviation = float(active.std(ddof=1))
    return float(active.mean() / deviation * math.sqrt(252.0)) if deviation else -math.inf


def load_daily(path: Path, *, split: str) -> tuple[pd.DataFrame, pd.Series]:
    con = duckdb.connect()
    minutes = (
        15,
        16,
        30,
        31,
        45,
        46,
        60,
        61,
        90,
        91,
        120,
        121,
        150,
        151,
        180,
        210,
        240,
        241,
        270,
        300,
        301,
        330,
        331,
        360,
        361,
        375,
        380,
        385,
    )
    decision_minutes = (15, 30, 45, 60, 90, 120, 150, 240, 300, 330, 360)
    value_columns = ",\n".join(
        [
            f"max(close) FILTER (WHERE minute = {minute}) AS close_{minute}, "
            f"max(open) FILTER (WHERE minute = {minute}) AS open_{minute}"
            for minute in minutes
        ]
        + [
            f"max(vix_level) FILTER (WHERE minute = {minute}) AS vix_{minute}, "
            f"exp(sum(spy_logret_1) FILTER (WHERE minute <= {minute})) - 1.0 "
            f"AS spy_current_{minute}"
            for minute in decision_minutes
        ]
        + [
            f"sum(close * volume) FILTER (WHERE minute <= {minute}) "
            f"/ nullif(sum(volume) FILTER (WHERE minute <= {minute}), 0) "
            f"AS vwap_{minute}, "
            f"sum(volume) FILTER (WHERE minute <= {minute}) AS cum_volume_{minute}, "
            f"max(high) FILTER (WHERE minute <= {minute}) AS range_high_{minute}, "
            f"min(low) FILTER (WHERE minute <= {minute}) AS range_low_{minute}"
            for minute in decision_minutes
        ]
    )
    query = f"""
        WITH localized AS (
            SELECT timezone('America/New_York', datetime) AS timestamp,
                   symbol, open, high, low, close, volume, spy_logret_1, vix_level
            FROM read_parquet(?)
        ), rth AS (
            SELECT *, CAST(timestamp AS DATE) AS session_date,
                   (date_part('hour', timestamp) - 9) * 60
                       + date_part('minute', timestamp) - 30 AS minute
            FROM localized
            WHERE CAST(timestamp AS TIME) >= TIME '09:30:00'
              AND CAST(timestamp AS TIME) < TIME '16:00:00'
        )
        SELECT symbol, session_date, count(DISTINCT minute) AS minutes,
               min(minute) AS first_minute, max(minute) AS last_minute,
               arg_min(open, timestamp) AS day_open,
               arg_max(close, timestamp) AS day_close,
               {value_columns}
        FROM rth
        GROUP BY symbol, session_date
        ORDER BY session_date, symbol
    """
    frame = con.execute(query, [str(path)]).fetch_df()
    frame = frame.loc[
        (frame["minutes"] >= MIN_COMPLETE_MINUTES)
        & (frame["first_minute"] <= 1)
        & (frame["last_minute"] >= 388)
    ].copy()
    benchmark_query = """
        WITH localized AS (
            SELECT timezone('America/New_York', datetime) AS timestamp,
                   spy_logret_1
            FROM read_parquet(?)
        ), unique_minutes AS (
            SELECT CAST(timestamp AS DATE) AS session_date, timestamp,
                   avg(spy_logret_1) AS spy_logret_1
            FROM localized
            WHERE CAST(timestamp AS TIME) >= TIME '09:30:00'
              AND CAST(timestamp AS TIME) < TIME '16:00:00'
            GROUP BY session_date, timestamp
        )
        SELECT session_date, exp(sum(spy_logret_1)) - 1.0 AS benchmark_return
        FROM unique_minutes
        GROUP BY session_date
        ORDER BY session_date
    """
    benchmark_frame = con.execute(benchmark_query, [str(path)]).fetch_df()
    benchmark = benchmark_frame.set_index("session_date")["benchmark_return"]
    frame["split"] = split
    print(
        json.dumps(
            {
                "split": split,
                "sessions": int(frame["session_date"].nunique()),
                "symbols": int(frame["symbol"].nunique()),
                "symbol_sessions": len(frame),
                "start": str(frame["session_date"].min()),
                "end": str(frame["session_date"].max()),
            },
            sort_keys=True,
        )
    )
    return frame, benchmark


def main() -> None:
    root = Path(os.environ.get("TWELVEDATA_ROOT", "E:/us-intraday-lab-data/twelvedata-http"))
    train, train_benchmark = load_daily(root / "bars_1min/train.parquet", split="train")
    validation, validation_benchmark = load_daily(
        root / "bars_1min/val.parquet", split="validation"
    )
    frame = pd.concat([train, validation], ignore_index=True)
    dates = pd.Index(sorted(frame["session_date"].unique()), name="session_date")
    train_dates = set(train["session_date"].unique())
    train_mask = pd.Series(dates.isin(train_dates), index=dates)
    benchmark = pd.concat([train_benchmark, validation_benchmark]).reindex(dates).fillna(0.0)
    symbols = tuple(sorted(frame["symbol"].unique()))

    def wide(column: str) -> pd.DataFrame:
        return frame.pivot(index="session_date", columns="symbol", values=column).reindex(
            index=dates, columns=symbols
        )

    day_open = wide("day_open")
    day_close = wide("day_close")
    prior_close = day_close.shift(1)
    gap = day_open / prior_close - 1.0
    prior_return = day_close.pct_change(fill_method=None).shift(1)
    trail3 = day_close.pct_change(3, fill_method=None).shift(1)
    close_at = {
        minute: wide(f"close_{minute}")
        for minute in (15, 30, 45, 60, 90, 120, 150, 180, 210, 240, 270, 300, 330, 360)
    }
    open_at = {
        minute: wide(f"open_{minute}")
        for minute in (
            16,
            31,
            46,
            60,
            61,
            90,
            91,
            120,
            121,
            150,
            151,
            180,
            240,
            241,
            300,
            301,
            330,
            331,
            360,
            361,
            375,
            380,
            385,
        )
    }
    vix_at = {
        minute: wide(f"vix_{minute}").median(axis=1)
        for minute in (15, 30, 45, 60, 90, 120, 150, 240, 300, 330, 360)
    }
    spy_current_at = {
        minute: wide(f"spy_current_{minute}").median(axis=1)
        for minute in (15, 30, 45, 60, 90, 120, 150, 240, 300, 330, 360)
    }
    vwap_at = {
        minute: wide(f"vwap_{minute}")
        for minute in (15, 30, 45, 60, 90, 120, 150, 240, 300, 330, 360)
    }
    cumulative_volume_at = {
        minute: wide(f"cum_volume_{minute}")
        for minute in (15, 30, 45, 60, 90, 120, 150, 240, 300, 330, 360)
    }
    range_high_at = {
        minute: wide(f"range_high_{minute}")
        for minute in (15, 30, 45, 60, 90, 120, 150, 240, 300, 330, 360)
    }
    range_low_at = {
        minute: wide(f"range_low_{minute}")
        for minute in (15, 30, 45, 60, 90, 120, 150, 240, 300, 330, 360)
    }
    passing: list[Result] = []
    scanned: list[Result] = []
    print(
        json.dumps(
            {
                "train_spy_rth_after_cost": metrics(
                    (benchmark - ROUND_TRIP_COST_1_5X).loc[train_mask]
                ),
                "validation_spy_rth_after_cost": metrics(
                    (benchmark - ROUND_TRIP_COST_1_5X).loc[~train_mask]
                ),
            },
            sort_keys=True,
        )
    )

    def evaluate(
        family: str,
        parameters: tuple[object, ...],
        selected: pd.DataFrame,
        raw: pd.DataFrame,
        gross: float,
    ) -> None:
        selected = selected.fillna(False)
        counts = selected.sum(axis=1).replace(0, np.nan)
        positions = selected.div(counts, axis=0).fillna(0.0) * gross
        stock_components = positions * (raw - ROUND_TRIP_COST_1_5X)
        for core_weight in (0.0,):
            core_component = core_weight * (benchmark - ROUND_TRIP_COST_1_5X)
            returns = stock_components.sum(axis=1).fillna(0.0) + core_component
            train_metrics = metrics(returns.loc[train_mask])
            dev = returns.loc[~train_mask]
            dev_metrics = metrics(dev)
            dev_benchmark = benchmark.loc[~train_mask]
            boundaries = np.linspace(0, len(dev), 5, dtype=int)
            folds = tuple(metrics(dev.iloc[boundaries[i] : boundaries[i + 1]])[0] for i in range(4))
            component_pnl = stock_components.loc[~train_mask].sum()
            component_pnl.loc["SPY_CORE"] = core_component.loc[~train_mask].sum()
            positive_pnl = component_pnl.clip(lower=0.0)
            concentration = (
                float(positive_pnl.max() / positive_pnl.sum())
                if float(positive_pnl.sum()) > 0.0
                else 1.0
            )
            result = Result(
                family=family,
                parameters=(*parameters, "core", core_weight),
                train_annual=train_metrics[0],
                validation_annual=dev_metrics[0],
                validation_ir=information_ratio(dev, dev_benchmark),
                validation_drawdown=dev_metrics[1],
                validation_profit_factor=dev_metrics[2],
                validation_trades=int(selected.loc[~train_mask].sum().sum())
                + (len(dev) if core_weight > 0.0 else 0),
                validation_concentration=concentration,
                folds=folds,
            )
            scanned.append(result)
            if (
                result.train_annual >= 0.08
                and result.validation_annual >= 0.10
                and result.validation_ir >= 0.50
                and result.validation_drawdown >= -0.08
                and result.validation_profit_factor >= 1.15
                and result.validation_trades >= 100
                and result.validation_concentration <= 0.70
                and sum(value > 0.0 for value in folds) >= 3
            ):
                passing.append(result)

    def bind_regime_evaluator(regime_map: dict[str, pd.Series], raw_returns: pd.DataFrame):
        def evaluate_regimes(
            family: str,
            parameters: tuple[object, ...],
            selected: pd.DataFrame,
            gross: float,
        ) -> None:
            for regime_name, regime in regime_map.items():
                evaluate(
                    family,
                    (*parameters, "regime", regime_name),
                    selected.mul(regime, axis=0),
                    raw_returns,
                    gross,
                )

        return evaluate_regimes

    for decision in (15, 30, 45, 60, 90, 120, 150, 240, 300, 330, 360):
        entry_minute = decision + 1
        current = close_at[decision] / day_open - 1.0
        recent = (
            current
            if decision == 15
            else close_at[decision] / close_at[max(15, decision - 30)] - 1.0
        )
        relative = current.sub(current.median(axis=1), axis=0)
        relative_volume = cumulative_volume_at[decision] / (
            cumulative_volume_at[decision].shift(1).rolling(20, min_periods=10).median()
        )
        range_width = range_high_at[decision] - range_low_at[decision]
        range_position = (close_at[decision] - range_low_at[decision]) / range_width
        above_vwap = close_at[decision] >= vwap_at[decision]
        regimes = {
            "all": pd.Series(True, index=dates),
            "spy_up": spy_current_at[decision] > 0.0,
            "spy_down": spy_current_at[decision] < 0.0,
            "vix_below_25": vix_at[decision] < 25.0,
            "vix_15_to_30": (vix_at[decision] >= 15.0) & (vix_at[decision] <= 30.0),
        }
        for exit_minute in (60, 90, 120, 150, 180, 240, 300, 330, 360, 375, 380, 385):
            if exit_minute <= entry_minute:
                continue
            raw = open_at[exit_minute] / open_at[entry_minute] - 1.0
            evaluate_regimes = bind_regime_evaluator(regimes, raw)

            for gross in (0.75, 1.0):
                for count in (3, 5, 8):
                    top_current = current.rank(axis=1, ascending=False, method="first") <= count
                    bottom_current = current.rank(axis=1, ascending=True, method="first") <= count
                    top_gap = gap.rank(axis=1, ascending=False, method="first") <= count
                    for floor in (0.0, 0.0015, 0.003, 0.005, 0.008):
                        evaluate_regimes(
                            "relative_momentum",
                            (decision, exit_minute, gross, count, floor),
                            top_current & (relative >= floor) & (recent > 0.0),
                            gross,
                        )
                    for ceiling in (-0.0015, -0.003, -0.005, -0.008, -0.012):
                        evaluate_regimes(
                            "relative_loser_reversal",
                            (decision, exit_minute, gross, count, ceiling),
                            bottom_current & (relative <= ceiling) & (recent < 0.0),
                            gross,
                        )
                    for bounce in (0.0, 0.0015, 0.003, 0.005):
                        evaluate_regimes(
                            "relative_pullback_recovery",
                            (decision, exit_minute, gross, count, bounce),
                            bottom_current
                            & (current < 0.0)
                            & (recent >= bounce)
                            & (trail3 > -0.15),
                            gross,
                        )
                    for confirm in (0.0, 0.0015, 0.003, 0.005):
                        evaluate_regimes(
                            "ranked_gap_continuation",
                            (decision, exit_minute, gross, count, confirm),
                            top_gap & (gap > 0.0) & (current >= confirm) & (recent >= 0.0),
                            gross,
                        )
                    score = (
                        current.rank(axis=1, pct=True)
                        + gap.rank(axis=1, pct=True)
                        + prior_return.rank(axis=1, pct=True)
                    )
                    top_score = score.rank(axis=1, ascending=False, method="first") <= count
                    evaluate_regimes(
                        "three_horizon_momentum",
                        (decision, exit_minute, gross, count),
                        top_score & (current > 0.0) & (recent > 0.0),
                        gross,
                    )
                    if decision <= 120:
                        for volume_floor in (1.0, 1.5, 2.0):
                            for strength_floor in (0.002, 0.005, 0.01):
                                evaluate_regimes(
                                    "volume_confirmed_strength",
                                    (
                                        decision,
                                        exit_minute,
                                        gross,
                                        count,
                                        volume_floor,
                                        strength_floor,
                                    ),
                                    top_current
                                    & (current >= strength_floor)
                                    & (relative_volume >= volume_floor)
                                    & above_vwap
                                    & (range_position >= 0.80),
                                    gross,
                                )
                        for volume_floor in (1.0, 1.5, 2.0):
                            for high_proximity in (0.995, 0.998, 0.9995):
                                evaluate_regimes(
                                    "opening_range_breakout",
                                    (
                                        decision,
                                        exit_minute,
                                        gross,
                                        count,
                                        volume_floor,
                                        high_proximity,
                                    ),
                                    top_current
                                    & (current > 0.0)
                                    & (relative_volume >= volume_floor)
                                    & above_vwap
                                    & (
                                        close_at[decision] / range_high_at[decision]
                                        >= high_proximity
                                    ),
                                    gross,
                                )

    print(
        json.dumps(
            {
                "scanned": len(scanned),
                "passing": len(passing),
                "gate_counts": {
                    "train_annual": sum(item.train_annual >= 0.08 for item in scanned),
                    "validation_annual": sum(item.validation_annual >= 0.10 for item in scanned),
                    "information_ratio": sum(item.validation_ir >= 0.50 for item in scanned),
                    "folds": sum(sum(value > 0.0 for value in item.folds) >= 3 for item in scanned),
                },
            },
            sort_keys=True,
        )
    )
    frontiers = {
        "passing": sorted(
            passing,
            key=lambda item: min(item.train_annual, item.validation_annual),
            reverse=True,
        )[:30],
        "balanced": sorted(
            scanned,
            key=lambda item: (min(item.train_annual, item.validation_annual), item.validation_ir),
            reverse=True,
        )[:20],
        "ir_positive_returns": sorted(
            (item for item in scanned if item.train_annual > 0.0 and item.validation_annual > 0.0),
            key=lambda item: (item.validation_ir, item.validation_annual),
            reverse=True,
        )[:20],
    }
    for frontier, items in frontiers.items():
        for item in items:
            print(json.dumps({"frontier": frontier, **asdict(item)}, sort_keys=True))


if __name__ == "__main__":
    main()
