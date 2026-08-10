"""Development-only scan of diversified stock and matched-SPY intraday sleeves."""

from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagnose_twelvedata_cross_section import load_daily

from us_intraday_lab.portfolio_research import annual_drawdown_profit_factor

COST = 0.0009
SPECS = (
    (Path("E:/us-intraday-lab-data/twelvedata-http/bars_1min/train.parquet"), "train"),
    (Path("E:/us-intraday-lab-data/twelvedata-http/bars_1min/val.parquet"), "2024"),
    (Path("E:/us-intraday-lab-data/twelvedata-http/bars_1min/test-2025.parquet"), "2025"),
)


def _metrics(returns: pd.Series, benchmark: pd.Series) -> dict[str, float]:
    annual, drawdown, profit_factor = annual_drawdown_profit_factor(returns)
    active = returns - benchmark
    deviation = float(active.std(ddof=1))
    information_ratio = (
        float(active.mean() / deviation * math.sqrt(252.0)) if deviation else -math.inf
    )
    return {
        "annualized_return": annual,
        "information_ratio": information_ratio,
        "max_drawdown": drawdown,
        "profit_factor": profit_factor,
    }


def main() -> None:
    frames = []
    periods: dict[str, tuple[object, ...]] = {}
    for path, period in SPECS:
        frame, _ = load_daily(path, split=period)
        frame["period"] = period
        frames.append(frame)
        periods[period] = tuple(sorted(frame["session_date"].unique()))
    joined = pd.concat(frames, ignore_index=True)
    dates = pd.Index(sorted(joined["session_date"].unique()), name="session_date")
    symbols = tuple(sorted(joined["symbol"].unique()))

    def wide(column: str) -> pd.DataFrame:
        return joined.pivot(index="session_date", columns="symbol", values=column).reindex(
            index=dates, columns=symbols
        )

    day_open = wide("day_open")
    features: dict[int, dict[str, pd.DataFrame | pd.Series]] = {}
    for decision in (30, 45, 60, 90):
        close = wide(f"close_{decision}")
        current = close / day_open - 1.0
        spy = wide(f"spy_current_{decision}").median(axis=1)
        volume = wide(f"cum_volume_{decision}")
        relative_volume = volume / volume.shift(1).rolling(20, min_periods=10).median()
        high = wide(f"range_high_{decision}")
        low = wide(f"range_low_{decision}")
        features[decision] = {
            "current": current,
            "ranks": current.rank(axis=1, ascending=False, method="first"),
            "excess": current.sub(spy, axis=0),
            "relative_volume": relative_volume,
            "range_position": (close - low) / (high - low),
            "above_vwap": close >= wide(f"vwap_{decision}"),
            "spy": spy,
        }
    entry_at = {minute: wide(f"open_{minute}") for minute in (31, 46, 61, 91)}
    exit_at = {minute: wide(f"open_{minute}") for minute in (240, 300, 330, 360)}
    spy_at = {
        minute: wide(f"spy_current_{minute}").median(axis=1) for minute in (240, 300, 330, 360)
    }

    records: list[dict[str, Any]] = []
    for (
        decision,
        exit_minute,
        count,
        current_floor,
        excess_floor,
        volume_floor,
        stock_weight,
    ) in itertools.product(
        (30, 45, 60, 90),
        (240, 300, 330, 360),
        (2, 3, 5),
        (0.002, 0.004, 0.006),
        (0.0025, 0.005, 0.0075),
        (1.0, 1.25, 1.5),
        (0.5, 0.67, 0.8),
    ):
        if exit_minute <= decision:
            continue
        feature = features[decision]
        current = feature["current"]
        assert isinstance(current, pd.DataFrame)
        ranks = feature["ranks"]
        excess = feature["excess"]
        relative_volume = feature["relative_volume"]
        range_position = feature["range_position"]
        above_vwap = feature["above_vwap"]
        spy_decision = feature["spy"]
        assert isinstance(excess, pd.DataFrame)
        assert isinstance(ranks, pd.DataFrame)
        assert isinstance(relative_volume, pd.DataFrame)
        assert isinstance(range_position, pd.DataFrame)
        assert isinstance(above_vwap, pd.DataFrame)
        assert isinstance(spy_decision, pd.Series)
        selected = (
            (ranks <= count)
            & (current >= current_floor)
            & (excess >= excess_floor)
            & (relative_volume >= volume_floor)
            & above_vwap
            & (range_position >= 0.60)
            & spy_decision.between(-0.002, 0.02).to_numpy()[:, None]
        ).fillna(False)
        counts = selected.sum(axis=1).replace(0, np.nan)
        positions = selected.div(counts, axis=0).fillna(0.0) * stock_weight
        stock_raw = exit_at[exit_minute] / entry_at[decision + 1] - 1.0
        stock_components = positions * (stock_raw - COST)
        stock_returns = stock_components.sum(axis=1).fillna(0.0)

        spy_exit = spy_at[exit_minute]
        spy_raw = (1.0 + spy_exit) / (1.0 + spy_decision) - 1.0
        spy_enabled = spy_decision.between(0.001, 0.02)
        market_weight = 1.0 - stock_weight
        market_returns = market_weight * (spy_raw - COST) * spy_enabled
        returns = stock_returns + market_returns
        benchmark = (stock_weight * spy_raw * selected.any(axis=1)) + (
            market_weight * spy_raw * spy_enabled
        )
        segment_metrics = {
            period: _metrics(returns.loc[list(sessions)], benchmark.loc[list(sessions)])
            for period, sessions in periods.items()
        }
        oos_sessions = periods["2024"] + periods["2025"]
        oos_returns = returns.loc[list(oos_sessions)]
        oos_benchmark = benchmark.loc[list(oos_sessions)]
        combined = _metrics(oos_returns, oos_benchmark)
        boundaries = np.linspace(0, len(oos_returns), 6, dtype=int)
        folds = tuple(
            annual_drawdown_profit_factor(
                oos_returns.iloc[boundaries[index] : boundaries[index + 1]]
            )[0]
            for index in range(5)
        )
        oos_mask = dates.isin(oos_sessions)
        trades = int(selected.loc[oos_mask].sum().sum() + spy_enabled.loc[oos_mask].sum())
        component_pnl = stock_components.loc[oos_mask].sum()
        component_pnl.loc["SPY"] = market_returns.loc[oos_mask].sum()
        positive = component_pnl.clip(lower=0.0)
        concentration = (
            float(positive.max() / positive.sum()) if float(positive.sum()) > 0.0 else 1.0
        )
        record = {
            "parameters": {
                "decision_minute": decision,
                "exit_minute": exit_minute,
                "stock_count": count,
                "current_floor": current_floor,
                "excess_floor": excess_floor,
                "relative_volume_floor": volume_floor,
                "stock_weight": stock_weight,
            },
            "train": segment_metrics["train"],
            "2024": segment_metrics["2024"],
            "2025": segment_metrics["2025"],
            "combined_oos": {
                **combined,
                "trades": trades,
                "positive_symbol_concentration": concentration,
                "folds": folds,
            },
        }
        record["passes_screen"] = (
            record["train"]["annualized_return"] >= 0.08
            and record["2024"]["annualized_return"] > 0.0
            and record["2025"]["annualized_return"] > 0.0
            and combined["annualized_return"] >= 0.10
            and combined["information_ratio"] >= 0.50
            and combined["max_drawdown"] <= 0.08
            and combined["profit_factor"] >= 1.15
            and trades >= 100
            and concentration <= 0.70
            and sum(value > 0.0 for value in folds) >= 3
        )
        records.append(record)

    passing = [record for record in records if record["passes_screen"]]
    passing.sort(
        key=lambda record: (
            min(
                record["train"]["annualized_return"],
                record["2024"]["annualized_return"],
                record["2025"]["annualized_return"],
            ),
            record["combined_oos"]["information_ratio"],
        ),
        reverse=True,
    )
    near = sorted(
        records,
        key=lambda record: (
            min(
                record["train"]["annualized_return"] / 0.08,
                record["combined_oos"]["annualized_return"] / 0.10,
                record["combined_oos"]["information_ratio"] / 0.50,
                0.08 / max(record["combined_oos"]["max_drawdown"], 1e-12),
                record["combined_oos"]["profit_factor"] / 1.15,
            ),
            record["combined_oos"]["annualized_return"],
        ),
        reverse=True,
    )
    print(
        json.dumps(
            {
                "scanned": len(records),
                "passing": len(passing),
                "gate_counts": {
                    "train_annual": sum(
                        record["train"]["annualized_return"] >= 0.08 for record in records
                    ),
                    "oos_annual": sum(
                        record["combined_oos"]["annualized_return"] >= 0.10 for record in records
                    ),
                    "oos_ir": sum(
                        record["combined_oos"]["information_ratio"] >= 0.50 for record in records
                    ),
                    "oos_drawdown": sum(
                        record["combined_oos"]["max_drawdown"] <= 0.08 for record in records
                    ),
                    "oos_profit_factor": sum(
                        record["combined_oos"]["profit_factor"] >= 1.15 for record in records
                    ),
                },
                "frontier": passing[:20],
                "near_frontier": near[:10],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
