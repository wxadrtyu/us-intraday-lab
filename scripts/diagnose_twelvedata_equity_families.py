"""Development-only causal scan of liquid-equity intraday strategy families.

The public Twelve Data test split is deliberately not read here.  Candidate
generation uses the historical train split and 2024 development split only.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

SYMBOLS = ("AAPL", "MSFT", "NVDA")
ROUND_TRIP_COST_1_5X = 0.0009
MAX_GROSS = 0.75
MIN_COMPLETE_MINUTES = 385


@dataclass(frozen=True)
class Candidate:
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


def _metrics(returns: pd.Series) -> tuple[float, float, float]:
    equity = (1.0 + returns).cumprod()
    annual = float(equity.iloc[-1] ** (252.0 / len(returns)) - 1.0)
    drawdown = float((equity / equity.cummax() - 1.0).min())
    gains = float(returns.clip(lower=0.0).sum())
    losses = abs(float(returns.clip(upper=0.0).sum()))
    return annual, drawdown, gains / losses if losses else math.inf


def _ir(returns: pd.Series, benchmark: pd.Series) -> float:
    active = returns - benchmark
    deviation = float(active.std(ddof=1))
    return float(active.mean() / deviation * math.sqrt(252.0)) if deviation else -math.inf


def _load(path: Path, *, split: str) -> pd.DataFrame:
    con = duckdb.connect()
    query = """
        WITH source AS (
            SELECT timezone('America/New_York', datetime) AS timestamp,
                   symbol, open, high, low, close, volume, spy_logret_1
            FROM read_parquet(?)
            WHERE symbol IN ('AAPL', 'MSFT', 'NVDA')
        )
        SELECT *
        FROM source
        WHERE CAST(timestamp AS TIME) >= TIME '09:30:00'
          AND CAST(timestamp AS TIME) < TIME '16:00:00'
        ORDER BY symbol, timestamp
    """
    frame = con.execute(query, [str(path)]).fetch_df()
    frame["session_date"] = frame["timestamp"].dt.date
    frame["minute"] = (frame["timestamp"].dt.hour - 9) * 60 + frame["timestamp"].dt.minute - 30
    quality = frame.groupby(["symbol", "session_date"], observed=True).agg(
        minutes=("minute", "nunique"),
        first_minute=("minute", "min"),
        last_minute=("minute", "max"),
    )
    good = quality.loc[
        (quality["minutes"] >= MIN_COMPLETE_MINUTES)
        & (quality["first_minute"] <= 1)
        & (quality["last_minute"] >= 388)
    ].reset_index()
    common = good.groupby("session_date", observed=True)["symbol"].nunique()
    common_dates = common.loc[common == len(SYMBOLS)].index
    frame = frame.loc[frame["session_date"].isin(common_dates)].copy()
    frame["split"] = split
    print(
        json.dumps(
            {
                "split": split,
                "raw_rows": len(quality),
                "common_complete_sessions": len(common_dates),
                "start": str(min(common_dates)),
                "end": str(max(common_dates)),
            },
            sort_keys=True,
        )
    )
    return frame


def _daily_features(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[int, pd.DataFrame]]:
    dates = pd.Index(sorted(frame["session_date"].unique()), name="session_date")
    daily = pd.DataFrame(index=dates)
    for symbol in SYMBOLS:
        symbol_frame = frame.loc[frame["symbol"] == symbol]
        symbol_group = symbol_frame.groupby("session_date", observed=True, sort=True)
        daily[(symbol, "open")] = symbol_group["open"].first().reindex(dates)
        daily[(symbol, "close")] = symbol_group["close"].last().reindex(dates)
        daily[(symbol, "prior_close")] = daily[(symbol, "close")].shift(1)
        daily[(symbol, "gap")] = daily[(symbol, "open")] / daily[(symbol, "prior_close")] - 1.0
        daily[(symbol, "prior_return")] = (
            daily[(symbol, "close")].pct_change(fill_method=None).shift(1)
        )
        daily[(symbol, "trail3")] = (
            daily[(symbol, "close")].pct_change(3, fill_method=None).shift(1)
        )
    spy = (
        frame.sort_values(["timestamp", "symbol"], kind="stable")
        .drop_duplicates(["session_date", "timestamp"])
        .groupby("session_date", observed=True)["spy_logret_1"]
        .sum()
        .reindex(dates)
    )
    daily[("SPY", "rth_return")] = np.expm1(spy)
    minute_frames: dict[int, pd.DataFrame] = {}
    wanted = (15, 30, 45, 60, 90, 120, 150, 180, 240, 300, 330)
    for minute in wanted:
        at_minute = frame.loc[frame["minute"] == minute]
        values = at_minute.pivot(index="session_date", columns="symbol")
        values = values.reindex(dates)
        minute_frames[minute] = values
    daily.columns = pd.MultiIndex.from_tuples(daily.columns)
    return daily, minute_frames


def main() -> None:
    data_root = Path(os.environ.get("TWELVEDATA_ROOT", "E:/us-intraday-lab-data/twelvedata-http"))
    train = _load(data_root / "bars_1min/train.parquet", split="train")
    validation = _load(data_root / "bars_1min/val.parquet", split="validation")
    train_dates = set(train["session_date"].unique())
    frame = pd.concat([train, validation], ignore_index=True)
    daily, minutes = _daily_features(frame)
    train_mask = pd.Series(daily.index.isin(train_dates), index=daily.index)
    results: list[Candidate] = []
    scanned: list[Candidate] = []

    def evaluate(
        family: str,
        parameters: tuple[object, ...],
        positions: pd.DataFrame,
        raw_returns: pd.DataFrame,
    ) -> None:
        positions = positions.fillna(0.0).clip(lower=0.0)
        gross = positions.sum(axis=1)
        scale = pd.Series(np.where(gross > MAX_GROSS, MAX_GROSS / gross, 1.0), index=gross.index)
        positions = positions.mul(scale, axis=0)
        components = positions * (raw_returns - ROUND_TRIP_COST_1_5X)
        returns = components.sum(axis=1).fillna(0.0)
        train_metrics = _metrics(returns.loc[train_mask])
        dev_returns = returns.loc[~train_mask]
        dev_metrics = _metrics(dev_returns)
        benchmark = daily.loc[~train_mask, ("SPY", "rth_return")].fillna(0.0)
        boundaries = np.linspace(0, len(dev_returns), 5, dtype=int)
        folds = tuple(
            _metrics(dev_returns.iloc[boundaries[i] : boundaries[i + 1]])[0] for i in range(4)
        )
        trades = int((positions.loc[~train_mask] > 0.0).sum().sum())
        pnl = components.loc[~train_mask].sum().clip(lower=0.0)
        concentration = float(pnl.max() / pnl.sum()) if float(pnl.sum()) > 0.0 else 1.0
        candidate = Candidate(
            family=family,
            parameters=parameters,
            train_annual=train_metrics[0],
            validation_annual=dev_metrics[0],
            validation_ir=_ir(dev_returns, benchmark),
            validation_drawdown=dev_metrics[1],
            validation_profit_factor=dev_metrics[2],
            validation_trades=trades,
            validation_concentration=concentration,
            folds=folds,
        )
        scanned.append(candidate)
        if (
            candidate.train_annual >= 0.08
            and candidate.validation_annual >= 0.10
            and candidate.validation_ir >= 0.50
            and candidate.validation_drawdown >= -0.08
            and candidate.validation_profit_factor >= 1.15
            and candidate.validation_trades >= 100
            and candidate.validation_concentration <= 0.70
            and sum(value > 0.0 for value in folds) >= 3
        ):
            results.append(candidate)

    for decision in (30, 45, 60, 90, 120, 150):
        signal_frame = minutes[decision]
        opens = daily.xs("open", axis=1, level=1).reindex(columns=SYMBOLS)
        current = signal_frame["close"].reindex(columns=SYMBOLS) / opens - 1.0
        recent_start = max(15, decision - 30)
        recent = (
            signal_frame["close"].reindex(columns=SYMBOLS)
            / minutes[recent_start]["close"].reindex(columns=SYMBOLS)
            - 1.0
        )
        gaps = daily.xs("gap", axis=1, level=1).reindex(columns=SYMBOLS)
        prior = daily.xs("prior_return", axis=1, level=1).reindex(columns=SYMBOLS)
        trail3 = daily.xs("trail3", axis=1, level=1).reindex(columns=SYMBOLS)
        for exit_minute in (120, 150, 180, 240, 300, 330):
            if exit_minute <= decision:
                continue
            entry = signal_frame["close"].reindex(columns=SYMBOLS)
            exit_prices = minutes[exit_minute]["close"].reindex(columns=SYMBOLS)
            raw = exit_prices / entry - 1.0
            for threshold in (0.0015, 0.0025, 0.004, 0.006, 0.009, 0.012, 0.018):
                eligible = (current >= threshold) & (recent > 0.0) & (gaps > -0.04)
                ranks = current.rank(axis=1, ascending=False, method="first")
                positions = eligible.astype(float) * (ranks <= 2).astype(float) * 0.375
                evaluate(
                    "confirmed_cross_momentum",
                    (decision, exit_minute, threshold),
                    positions,
                    raw,
                )
            for gap_floor in (0.0025, 0.005, 0.008, 0.012, 0.018, 0.025):
                for confirm in (0.0, 0.0015, 0.003, 0.005):
                    eligible = (gaps >= gap_floor) & (current >= confirm) & (recent >= 0.0)
                    positions = eligible.astype(float) * 0.25
                    evaluate(
                        "gap_continuation",
                        (decision, exit_minute, gap_floor, confirm),
                        positions,
                        raw,
                    )
            for gap_ceiling in (-0.005, -0.008, -0.012, -0.018, -0.025, -0.04):
                for bounce in (0.0015, 0.003, 0.005, 0.008):
                    eligible = (gaps <= gap_ceiling) & (current >= bounce) & (recent > 0.0)
                    positions = eligible.astype(float) * 0.25
                    evaluate(
                        "gap_down_recovery",
                        (decision, exit_minute, gap_ceiling, bounce),
                        positions,
                        raw,
                    )
            for pullback in (-0.004, -0.006, -0.009, -0.012, -0.018, -0.025):
                for bounce in (0.001, 0.0025, 0.004, 0.006):
                    eligible = (
                        (current <= pullback)
                        & (recent >= bounce)
                        & (prior > -0.05)
                        & (trail3 > -0.10)
                    )
                    ranks = current.rank(axis=1, ascending=True, method="first")
                    positions = eligible.astype(float) * (ranks <= 2).astype(float) * 0.375
                    evaluate(
                        "cross_pullback_recovery",
                        (decision, exit_minute, pullback, bounce),
                        positions,
                        raw,
                    )

    ordered = sorted(
        results,
        key=lambda item: (min(item.train_annual, item.validation_annual), item.validation_ir),
        reverse=True,
    )
    for candidate in ordered[:50]:
        print(json.dumps(candidate.__dict__, sort_keys=True))
    eligible_activity = [item for item in scanned if item.validation_trades >= 100]
    frontiers = {
        "balanced_annual": sorted(
            eligible_activity,
            key=lambda item: (min(item.train_annual, item.validation_annual), item.validation_ir),
            reverse=True,
        )[:10],
        "validation_annual": sorted(
            (item for item in eligible_activity if item.train_annual > 0.0),
            key=lambda item: (item.validation_annual, item.validation_ir),
            reverse=True,
        )[:10],
        "information_ratio": sorted(
            (
                item
                for item in eligible_activity
                if item.train_annual > 0.0 and item.validation_annual > 0.0
            ),
            key=lambda item: (item.validation_ir, item.validation_annual),
            reverse=True,
        )[:10],
    }
    gate_counts = {
        "train_annual": sum(item.train_annual >= 0.08 for item in scanned),
        "validation_annual": sum(item.validation_annual >= 0.10 for item in scanned),
        "information_ratio": sum(item.validation_ir >= 0.50 for item in scanned),
        "drawdown": sum(item.validation_drawdown >= -0.08 for item in scanned),
        "profit_factor": sum(item.validation_profit_factor >= 1.15 for item in scanned),
        "trades": sum(item.validation_trades >= 100 for item in scanned),
        "concentration": sum(item.validation_concentration <= 0.70 for item in scanned),
        "folds": sum(sum(value > 0.0 for value in item.folds) >= 3 for item in scanned),
    }
    print(json.dumps({"gate_counts": gate_counts, "scanned": len(scanned)}, sort_keys=True))
    for name, candidates in frontiers.items():
        for candidate in candidates:
            print(json.dumps({"frontier": name, **candidate.__dict__}, sort_keys=True))
    print(f"passing_cells={len(results)}")


if __name__ == "__main__":
    main()
