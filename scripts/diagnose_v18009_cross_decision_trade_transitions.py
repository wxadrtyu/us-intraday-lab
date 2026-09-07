"""Training-only causal screen of cross-decision trade-print transitions."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

DECISIONS = (5, 11, 17, 23)
TOP_COUNTS = (1, 2, 3, 5, 10)
EXITS = {1: "p2_open", 2: "p3_open", 4: "p5_open", 6: "p7_open"}
FAMILIES = (
    "trade_availability_activation",
    "activity_burst_continuation",
    "positive_location_flip_reversal",
    "persistent_sell_pressure_exhaustion",
    "print_discount_deepening_reversal",
    "print_discount_recovery_continuation",
)


def metrics(series: pd.Series) -> dict[str, float | int]:
    clean = series.fillna(0.0).astype(float)
    index = pd.DatetimeIndex(clean.index)
    wealth = (1.0 + clean).cumprod()
    drawdown = wealth / wealth.cummax() - 1.0
    annualized = math.exp(float(np.log1p(clean.clip(lower=-0.999999)).sum()) * 252.0 / len(clean)) - 1.0
    volatility = float(clean.std(ddof=1))
    year_returns = [float(np.prod(1.0 + clean.loc[index.year == year].to_numpy()) - 1.0) for year in sorted(set(index.year))]
    return {
        "annualized_return": annualized,
        "max_drawdown": float(-drawdown.min()),
        "information_ratio": float(clean.mean() / volatility * math.sqrt(252.0)) if volatility > 0 else 0.0,
        "positive_calendar_years": sum(value > 0 for value in year_returns),
    }


def family_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    current = frame["trade_available"].fillna(False)
    previous = frame["prev_trade_available"].fillna(False)
    if family == FAMILIES[0]:
        return current & ~previous & frame["ret1"].gt(0)
    if family == FAMILIES[1]:
        return current & previous & frame["activity_change"].gt(0) & frame["ret1"].gt(0)
    if family == FAMILIES[2]:
        return current & previous & frame["prev_imbalance"].lt(0) & frame["trade_location_volume_imbalance"].gt(0) & frame["ret1"].lt(0)
    if family == FAMILIES[3]:
        return current & previous & frame["prev_imbalance"].lt(0) & frame["trade_location_volume_imbalance"].lt(0) & frame["ret1"].lt(0)
    if family == FAMILIES[4]:
        return current & previous & frame["last_trade_edge_to_midpoint"].lt(0) & frame["edge_change"].lt(0) & frame["ret1"].lt(0)
    if family == FAMILIES[5]:
        return current & previous & frame["prev_edge"].lt(0) & frame["edge_change"].gt(0) & frame["ret1"].gt(0)
    raise ValueError(family)


def family_score(frame: pd.DataFrame, family: str) -> pd.Series:
    down = -frame["ret1"].rank(pct=True)
    up = frame["ret1"].rank(pct=True)
    if family == FAMILIES[0]:
        return frame["activity_change"].rank(pct=True) + up
    if family == FAMILIES[1]:
        return frame["activity_change"].rank(pct=True) + up
    if family == FAMILIES[2]:
        return frame["imbalance_change"].rank(pct=True) + down
    if family == FAMILIES[3]:
        return -frame["trade_location_volume_imbalance"].rank(pct=True) + down
    if family == FAMILIES[4]:
        return -frame["edge_change"].rank(pct=True) + down
    if family == FAMILIES[5]:
        return frame["edge_change"].rank(pct=True) + up
    raise ValueError(family)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument("--output", default="research/results/2026-09-07-v18009-cross-decision-trade-transition-diagnostic.json")
    args = parser.parse_args()
    started = time.monotonic()
    root = Path(args.data_root) / "research/cache"
    events = pd.read_parquet(root / "v14309_v14408_events.parquet")
    trades = pd.read_parquet(root / "us_market_event_trade_features_1s_v1.parquet")
    for frame in (events, trades):
        frame["session_date"] = pd.to_datetime(frame["session_date"])
    events = events.loc[events["session_date"].between("2021-01-01", "2023-12-31")]
    trade_columns = ["symbol", "session_date", "bar_idx", "trade_available", "volume_1s", "trade_location_volume_imbalance", "last_trade_edge_to_midpoint"]
    frame = events.merge(trades[trade_columns], on=["symbol", "session_date", "bar_idx"], how="left", validate="one_to_one").sort_values(["symbol", "session_date", "bar_idx"])
    grouped = frame.groupby(["symbol", "session_date"], sort=False)
    frame["prev_bar_idx"] = grouped["bar_idx"].shift(1)
    frame["prev_trade_available"] = grouped["trade_available"].shift(1)
    frame["prev_volume_1s"] = grouped["volume_1s"].shift(1)
    frame["prev_imbalance"] = grouped["trade_location_volume_imbalance"].shift(1)
    frame["prev_edge"] = grouped["last_trade_edge_to_midpoint"].shift(1)
    frame["activity_change"] = np.log1p(frame["volume_1s"]) - np.log1p(frame["prev_volume_1s"])
    frame["imbalance_change"] = frame["trade_location_volume_imbalance"] - frame["prev_imbalance"]
    frame["edge_change"] = frame["last_trade_edge_to_midpoint"] - frame["prev_edge"]
    records: list[dict[str, object]] = []
    for family in FAMILIES:
        qualifying = frame.loc[family_mask(frame, family)].copy()
        qualifying["score"] = family_score(qualifying, family)
        for decision in DECISIONS:
            calendar = pd.DatetimeIndex(sorted(frame.loc[frame["bar_idx"].eq(decision), "session_date"].unique()))
            eligible = qualifying.loc[qualifying["bar_idx"].eq(decision)].sort_values(["session_date", "score", "symbol"], ascending=[True, False, True]).copy()
            eligible["selection_rank"] = eligible.groupby("session_date").cumcount() + 1
            for top_count in TOP_COUNTS:
                selected = eligible.loc[eligible["selection_rank"] <= top_count]
                traded_days = pd.DatetimeIndex(selected["session_date"].drop_duplicates())
                for holding, exit_column in EXITS.items():
                    raw = (selected[exit_column] / selected["p1_open"] - 1.0).groupby(selected["session_date"]).mean().reindex(calendar, fill_value=0.0)
                    daily = raw.copy()
                    daily.loc[traded_days] -= 0.0009
                    evaluated = metrics(daily)
                    records.append({"family": family, "decision_bar": decision, "top_count": top_count, "holding_bars": holding, "signal_sessions": len(traded_days), **evaluated})
    for record in records:
        record["retention_floor_passed"] = bool(int(str(record["signal_sessions"])) >= 120 and float(str(record["annualized_return"])) >= 0.20 and float(str(record["information_ratio"])) >= 0.80 and int(str(record["positive_calendar_years"])) >= 2)
    records.sort(key=lambda item: (bool(item["retention_floor_passed"]), float(str(item["annualized_return"])), float(str(item["information_ratio"]))), reverse=True)
    result = {"schema_version": "1.0.0", "status": "COMPLETE", "diagnostic_id": "v18009-cross-decision-trade-transition-training-screen", "period": "2021-01-01/2023-12-31", "development_or_consumed_loaded": False, "cells_completed": len(records), "retained_cells": sum(bool(item["retention_floor_passed"]) for item in records), "elapsed_seconds": time.monotonic() - started, "records_by_training_rank": records}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(result, indent=2) + "\n", "utf-8")
    temporary.replace(output)
    print(json.dumps({key: result[key] for key in ("status", "cells_completed", "retained_cells", "elapsed_seconds")}, indent=2))


if __name__ == "__main__":
    main()
