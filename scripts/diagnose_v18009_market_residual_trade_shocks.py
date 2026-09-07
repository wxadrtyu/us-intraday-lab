"""Training-only screen of causal market-residual trade-print shocks."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

DECISIONS = (2, 5, 11, 17, 23)
TOP_COUNTS = (1, 2, 3, 5, 10)
EXITS = {1: "p2_open", 2: "p3_open", 4: "p5_open", 6: "p7_open"}
FAMILIES = (
    "buy_pressure_against_price_underperformance",
    "activity_absorption_reversal",
    "print_resilience_reversal",
    "confirmed_idiosyncratic_momentum",
    "market_selloff_relative_laggard_reversal",
    "calm_market_idiosyncratic_reversal",
)


def metrics(series: pd.Series) -> dict[str, float | int]:
    clean = series.fillna(0.0).astype(float)
    index = pd.DatetimeIndex(clean.index)
    wealth = (1.0 + clean).cumprod()
    drawdown = wealth / wealth.cummax() - 1.0
    annualized = math.exp(float(np.log1p(clean.clip(lower=-0.999999)).sum()) * 252.0 / len(clean)) - 1.0
    volatility = float(clean.std(ddof=1))
    year_returns = [float(np.prod(1.0 + clean.loc[index.year == year].to_numpy()) - 1.0) for year in sorted(set(index.year))]
    return {"annualized_return": annualized, "max_drawdown": float(-drawdown.min()), "information_ratio": float(clean.mean() / volatility * math.sqrt(252.0)) if volatility > 0 else 0.0, "positive_calendar_years": sum(value > 0 for value in year_returns)}


def family_mask(frame: pd.DataFrame, family: str) -> pd.Series:
    valid = frame["trade_available"].fillna(False)
    low_price = frame["ret_resid_rank"] <= 0.10
    high_price = frame["ret_resid_rank"] >= 0.90
    high_activity = frame["activity_resid_rank"] >= 0.75
    high_buy = frame["imbalance_resid_rank"] >= 0.75
    high_edge = frame["edge_resid_rank"] >= 0.75
    if family == FAMILIES[0]:
        return valid & low_price & high_buy
    if family == FAMILIES[1]:
        return valid & low_price & high_activity & frame["response_efficiency_rank"].le(0.50)
    if family == FAMILIES[2]:
        return valid & low_price & high_edge
    if family == FAMILIES[3]:
        return valid & high_price & high_activity & high_buy
    if family == FAMILIES[4]:
        return valid & low_price & high_edge & frame["market_ret1"].lt(-0.001)
    if family == FAMILIES[5]:
        return valid & low_price & high_buy & frame["market_ret1"].abs().le(0.001)
    raise ValueError(family)


def family_score(frame: pd.DataFrame, family: str) -> pd.Series:
    down = 1.0 - frame["ret_resid_rank"]
    up = frame["ret_resid_rank"]
    if family == FAMILIES[0]:
        return down + frame["imbalance_resid_rank"]
    if family == FAMILIES[1]:
        return down + frame["activity_resid_rank"] - frame["response_efficiency_rank"]
    if family == FAMILIES[2]:
        return down + frame["edge_resid_rank"]
    if family == FAMILIES[3]:
        return up + frame["activity_resid_rank"] + frame["imbalance_resid_rank"]
    if family == FAMILIES[4]:
        return down + frame["edge_resid_rank"] - frame["market_ret1"]
    if family == FAMILIES[5]:
        return down + frame["imbalance_resid_rank"] - frame["market_ret1"].abs()
    raise ValueError(family)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument("--output", default="research/results/2026-09-07-v18009-market-residual-trade-diagnostic.json")
    args = parser.parse_args()
    started = time.monotonic()
    root = Path(args.data_root) / "research/cache"
    events = pd.read_parquet(root / "v14309_v14408_events.parquet")
    trades = pd.read_parquet(root / "us_market_event_trade_features_1s_v1.parquet")
    for data in (events, trades):
        data["session_date"] = pd.to_datetime(data["session_date"])
    events = events.loc[events["session_date"].between("2021-01-01", "2023-12-31")]
    columns = ["symbol", "session_date", "bar_idx", "trade_available", "volume_1s", "trade_location_volume_imbalance", "last_trade_edge_to_midpoint"]
    frame = events.merge(trades[columns], on=["symbol", "session_date", "bar_idx"], how="left", validate="one_to_one")
    keys = ["session_date", "bar_idx"]
    frame["log_activity"] = np.log1p(frame["volume_1s"])
    medians = frame.groupby(keys, as_index=False).agg(market_ret1=("ret1", "median"), market_log_activity=("log_activity", "median"), market_imbalance=("trade_location_volume_imbalance", "median"), market_edge=("last_trade_edge_to_midpoint", "median"))
    frame = frame.merge(medians, on=keys, how="left", validate="many_to_one")
    frame["ret_resid"] = frame["ret1"] - frame["market_ret1"]
    frame["activity_resid"] = frame["log_activity"] - frame["market_log_activity"]
    frame["imbalance_resid"] = frame["trade_location_volume_imbalance"] - frame["market_imbalance"]
    frame["edge_resid"] = frame["last_trade_edge_to_midpoint"] - frame["market_edge"]
    frame["response_efficiency"] = frame["ret_resid"].abs() / (frame["activity_resid"].abs() + 0.05)
    for column in ("ret_resid", "activity_resid", "imbalance_resid", "edge_resid", "response_efficiency"):
        frame[f"{column}_rank"] = frame.groupby(keys)[column].rank(pct=True)
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
    result = {"schema_version": "1.0.0", "status": "COMPLETE", "diagnostic_id": "v18009-market-residual-trade-shock-training-screen", "period": "2021-01-01/2023-12-31", "development_or_consumed_loaded": False, "industry_mapping": "UNAVAILABLE", "cells_completed": len(records), "retained_cells": sum(bool(item["retention_floor_passed"]) for item in records), "elapsed_seconds": time.monotonic() - started, "records_by_training_rank": records}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(result, indent=2) + "\n", "utf-8")
    temporary.replace(output)
    print(json.dumps({key: result[key] for key in ("status", "cells_completed", "retained_cells", "elapsed_seconds")}, indent=2))


if __name__ == "__main__":
    main()
