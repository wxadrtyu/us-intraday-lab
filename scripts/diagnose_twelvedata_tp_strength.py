"""Research-only exact-minute scan of take-profit relative-strength variants."""

from __future__ import annotations

import itertools
import json
import math
import sys
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from diagnose_twelvedata_cross_section import load_daily

from us_intraday_lab.portfolio_research import (
    annual_drawdown_profit_factor,
    information_ratio,
)

COST = 0.0009
SPECS = (
    ("E:/us-intraday-lab-data/twelvedata-http/bars_1min/train.parquet", "train"),
    ("E:/us-intraday-lab-data/twelvedata-http/bars_1min/val.parquet", "2024"),
    ("E:/us-intraday-lab-data/twelvedata-http/bars_1min/test-2025.parquet", "2025"),
)


def _load_candidates() -> tuple[pd.DataFrame, tuple[pd.DataFrame, ...], pd.Index]:
    frames = []
    for path, period in SPECS:
        frame, _ = load_daily(Path(path), split=period)
        frame["period"] = period
        frames.append(frame)
    joined = pd.concat(frames, ignore_index=True)
    dates = pd.Index(sorted(joined["session_date"].unique()), name="session_date")
    symbols = tuple(sorted(joined["symbol"].unique()))

    def wide(column: str) -> pd.DataFrame:
        return joined.pivot(index="session_date", columns="symbol", values=column).reindex(
            index=dates, columns=symbols
        )

    day_open = wide("day_open")
    close = wide("close_45")
    entry = wide("open_46")
    volume = wide("cum_volume_45")
    vwap = wide("vwap_45")
    high = wide("range_high_45")
    low = wide("range_low_45")
    spy = wide("spy_current_45").median(axis=1)
    current = close / day_open - 1.0
    excess = current.sub(spy, axis=0)
    relative_volume = volume / volume.shift(1).rolling(20, min_periods=10).median()
    range_position = (close - low) / (high - low)
    ranks = current.rank(axis=1, ascending=False, method="first")
    loose = (
        (ranks <= 3)
        & (current >= 0.003)
        & (excess >= 0.005)
        & (relative_volume >= 1.2)
        & (close >= vwap)
        & (range_position >= 0.6)
        & (spy >= -0.002).to_numpy()[:, None]
        & (spy <= 0.03).to_numpy()[:, None]
    ).fillna(False)
    candidates = loose.stack()
    candidates = candidates[candidates].reset_index()[["session_date", "symbol"]]
    period_by_date = {
        session: period
        for frame, (_, period) in zip(frames, SPECS, strict=True)
        for session in frame["session_date"].unique()
    }
    for name, values in {
        "entry": entry,
        "rank": ranks,
        "excess": excess,
        "relative_volume": relative_volume,
        "range_position": range_position,
        "exit_330": wide("open_330"),
        "exit_360": wide("open_360"),
    }.items():
        candidates[name] = [
            float(values.loc[row.session_date, row.symbol]) for row in candidates.itertuples()
        ]
    candidates["spy_45"] = candidates["session_date"].map(spy)
    candidates["period"] = candidates["session_date"].map(period_by_date)
    candidates["trade_id"] = range(len(candidates))
    return candidates, tuple(frames), dates


def _minute_outcomes(
    candidates: pd.DataFrame,
) -> dict[tuple[int, int, float | None], tuple[float, float]]:
    connection = duckdb.connect()
    connection.register("signals", candidates[["trade_id", "session_date", "symbol"]])
    paths = ",".join(f"'{path}'" for path, _ in SPECS)
    bars = connection.execute(
        f"""
        WITH source AS (
            SELECT timezone('America/New_York', datetime) AS timestamp,
                   symbol, high, spy_logret_1,
                   (date_part('hour', timezone('America/New_York', datetime)) - 9) * 60
                     + date_part('minute', timezone('America/New_York', datetime)) - 30
                       AS minute_index
            FROM read_parquet([{paths}])
        )
        SELECT signals.trade_id, source.minute_index, source.high, source.spy_logret_1
        FROM signals
        JOIN source ON source.symbol = signals.symbol
          AND CAST(source.timestamp AS DATE) = signals.session_date
        WHERE source.minute_index >= 46 AND source.minute_index < 360
        ORDER BY signals.trade_id, source.minute_index
        """
    ).fetch_df()
    connection.close()
    grouped = {int(key): value for key, value in bars.groupby("trade_id", sort=True)}
    outcomes = {}
    for row in candidates.itertuples():
        trade_bars = grouped[int(row.trade_id)]
        for exit_minute, take_profit in itertools.product((330, 360), (None, 0.015, 0.02)):
            eligible = trade_bars.loc[trade_bars["minute_index"] < exit_minute]
            hits = (
                eligible.loc[eligible["high"] >= float(row.entry) * (1.0 + take_profit)]
                if take_profit is not None
                else eligible.iloc[0:0]
            )
            if len(hits):
                used = eligible.loc[: hits.index[0]]
                stock_return = float(take_profit)
            else:
                used = eligible
                stock_return = float(getattr(row, f"exit_{exit_minute}")) / float(row.entry) - 1.0
            benchmark_return = math.expm1(float(used["spy_logret_1"].sum()))
            outcomes[(int(row.trade_id), exit_minute, take_profit)] = (
                stock_return - COST,
                benchmark_return,
            )
    return outcomes


def main() -> None:
    candidates, frames, dates = _load_candidates()
    outcomes = _minute_outcomes(candidates)
    periods = {
        period: tuple(sorted(frame["session_date"].unique()))
        for frame, (_, period) in zip(frames, SPECS, strict=True)
    }
    records: list[dict[str, Any]] = []
    for values in itertools.product(
        (330, 360),
        (None, 0.015, 0.02),
        (1, 3),
        (1.2, 1.5),
        (0.005, 0.01, 0.015),
        (0.6, 0.7),
        (-0.002, 0.0, 0.002),
        (0.015, 0.03),
    ):
        (
            exit_minute,
            take_profit,
            count,
            volume_floor,
            excess_floor,
            range_floor,
            spy_min,
            spy_max,
        ) = values
        selected = candidates.loc[
            (candidates["rank"] <= count)
            & (candidates["relative_volume"] >= volume_floor)
            & (candidates["excess"] >= excess_floor)
            & (candidates["range_position"] >= range_floor)
            & (candidates["spy_45"] >= spy_min)
            & (candidates["spy_45"] <= spy_max)
        ]
        strategy = pd.Series(0.0, index=dates)
        benchmark = pd.Series(0.0, index=dates)
        components: dict[str, float] = {}
        for session, group in selected.groupby("session_date", sort=True):
            weight = 1.0 / len(group)
            for row in group.itertuples():
                stock_return, benchmark_return = outcomes[
                    (int(row.trade_id), int(exit_minute), take_profit)
                ]
                strategy.loc[session] += weight * stock_return
                benchmark.loc[session] += weight * benchmark_return
                components[str(row.symbol)] = (
                    components.get(str(row.symbol), 0.0) + weight * stock_return
                )
        segment_metrics = {}
        for period, sessions in periods.items():
            returns = strategy.loc[list(sessions)]
            annual, drawdown, profit_factor = annual_drawdown_profit_factor(returns)
            segment_metrics[period] = {
                "annualized_return": annual,
                "max_drawdown": drawdown,
                "profit_factor": profit_factor,
                "trades": int((selected["period"] == period).sum()),
            }
        oos_sessions = periods["2024"] + periods["2025"]
        oos_returns = strategy.loc[list(oos_sessions)]
        annual, drawdown, profit_factor = annual_drawdown_profit_factor(oos_returns)
        boundaries = np.linspace(0, len(oos_returns), 6, dtype=int)
        folds = tuple(
            annual_drawdown_profit_factor(
                oos_returns.iloc[boundaries[index] : boundaries[index + 1]]
            )[0]
            for index in range(5)
        )
        positive = {symbol: value for symbol, value in components.items() if value > 0.0}
        concentration = max(positive.values()) / sum(positive.values()) if positive else 1.0
        record = {
            "parameters": values,
            "segments": segment_metrics,
            "combined_oos": {
                "annualized_return": annual,
                "information_ratio": information_ratio(
                    oos_returns, benchmark.loc[list(oos_sessions)]
                ),
                "max_drawdown": drawdown,
                "profit_factor": profit_factor,
                "trades": int((selected["period"] != "train").sum()),
                "positive_symbol_concentration": concentration,
                "folds": folds,
            },
        }
        combined = record["combined_oos"]
        record["passes_screen"] = (
            combined["annualized_return"] >= 0.10
            and combined["information_ratio"] >= 0.50
            and combined["max_drawdown"] <= 0.08
            and combined["profit_factor"] >= 1.15
            and combined["trades"] >= 100
            and combined["positive_symbol_concentration"] <= 0.70
            and sum(value > 0.0 for value in folds) >= 3
            and all(item["annualized_return"] > 0.0 for item in segment_metrics.values())
        )
        records.append(record)
    passing = [record for record in records if record["passes_screen"]]
    passing.sort(
        key=lambda record: (
            min(item["annualized_return"] for item in record["segments"].values()),
            record["combined_oos"]["annualized_return"],
            record["combined_oos"]["information_ratio"],
        ),
        reverse=True,
    )
    print(
        json.dumps(
            {
                "candidate_trades": len(candidates),
                "scanned": len(records),
                "passing": len(passing),
                "frontier": passing[:30],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
