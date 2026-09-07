"""Preregistered training-only opening-climax frequency diagnostic."""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd

SHOCKS = (0.006, 0.008, 0.010, 0.012)
VOLUME_FLOORS = (0.80, 0.85, 0.90, 0.95)
RANGE_CEILINGS = (0.20, 0.30, 0.40)
MARKET_QUANTILES = (0.50, 0.65, 0.75, 0.85)
TOP_COUNTS = (1, 2, 3, 5, 10)
EXITS = {1: "p2_open", 2: "p3_open", 4: "p5_open", 6: "p7_open"}


def metrics(series: pd.Series) -> dict[str, float | int]:
    clean = series.fillna(0.0).astype(float)
    wealth = (1.0 + clean).cumprod()
    drawdown = wealth / wealth.cummax() - 1.0
    date_index = pd.DatetimeIndex(clean.index)
    years = sorted(set(date_index.year))
    year_returns = [float(np.prod(1.0 + clean.loc[date_index.year == year].to_numpy()) - 1.0) for year in years]
    annualized = math.exp(float(np.log1p(clean.clip(lower=-0.999999)).sum()) * 252.0 / len(clean)) - 1.0
    volatility = float(clean.std(ddof=1))
    return {
        "annualized_return": annualized,
        "max_drawdown": float(-drawdown.min()),
        "information_ratio": float(clean.mean() / volatility * math.sqrt(252.0)) if volatility > 0 else 0.0,
        "positive_calendar_years": sum(value > 0 for value in year_returns),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument("--output", default="research/results/2026-09-07-v18009-training-frequency-diagnostic.json")
    args = parser.parse_args()
    started = time.monotonic()
    root = Path(args.data_root)
    events = pd.read_parquet(root / "research/cache/v14309_v14408_events.parquet")
    trades = pd.read_parquet(root / "research/cache/us_market_event_trade_features_1s_v1.parquet")
    for frame in (events, trades):
        frame["session_date"] = pd.to_datetime(frame["session_date"])
    events = events.loc[events["session_date"].between("2021-01-01", "2023-12-31") & events["bar_idx"].eq(2)].copy()
    calendar = pd.DatetimeIndex(sorted(events["session_date"].unique()))
    events["volume_rank"] = events.groupby("session_date")["volume"].rank(pct=True)
    state = events.groupby("session_date", as_index=False).agg(median_abs_ret3=("ret3", lambda values: float(values.abs().median())))
    events = events.merge(state, on="session_date", how="left", validate="many_to_one")
    trade_columns = ["symbol", "session_date", "bar_idx", "trade_available", "last_trade_edge_to_midpoint"]
    events = events.merge(trades[trade_columns], on=["symbol", "session_date", "bar_idx"], how="left", validate="one_to_one")
    events = events.loc[events["trade_available"].fillna(False) & events["last_trade_edge_to_midpoint"].le(0)].copy()
    events["score"] = -events["ret1"] + events["volume_rank"] - events["range_pos"] - events["last_trade_edge_to_midpoint"].rank(pct=True)
    market_thresholds = {quantile: float(state["median_abs_ret3"].quantile(quantile)) for quantile in MARKET_QUANTILES}
    records: list[dict[str, object]] = []
    for shock in SHOCKS:
        for volume_floor in VOLUME_FLOORS:
            for range_ceiling in RANGE_CEILINGS:
                for market_quantile, market_threshold in market_thresholds.items():
                    eligible = events.loc[(events["ret1"] <= -shock) & (events["volume_rank"] >= volume_floor) & (events["range_pos"] <= range_ceiling) & (events["median_abs_ret3"] >= market_threshold)].sort_values(["session_date", "score", "symbol"], ascending=[True, False, True]).copy()
                    eligible["selection_rank"] = eligible.groupby("session_date").cumcount() + 1
                    for top_count in TOP_COUNTS:
                        selected = eligible.loc[eligible["selection_rank"] <= top_count]
                        traded_days = pd.DatetimeIndex(selected["session_date"].drop_duplicates())
                        for holding, exit_column in EXITS.items():
                            raw = (selected[exit_column] / selected["p1_open"] - 1.0).groupby(selected["session_date"]).mean().reindex(calendar, fill_value=0.0)
                            daily = raw.copy()
                            daily.loc[traded_days] -= 0.0009
                            evaluated = metrics(daily)
                            records.append({"downshock_abs": shock, "volume_rank_floor": volume_floor, "range_position_ceiling": range_ceiling, "market_absolute_activity_quantile": market_quantile, "top_count": top_count, "holding_bars": holding, "signal_sessions": len(traded_days), **evaluated})
    for record in records:
        record["retention_floor_passed"] = bool(int(str(record["signal_sessions"])) >= 120 and float(str(record["annualized_return"])) >= 0.20 and float(str(record["information_ratio"])) >= 0.80 and int(str(record["positive_calendar_years"])) >= 2)
    records.sort(key=lambda item: (bool(item["retention_floor_passed"]), float(str(item["annualized_return"])), float(str(item["information_ratio"]))), reverse=True)
    result = {
        "schema_version": "1.0.0", "status": "COMPLETE",
        "diagnostic_id": "v18009-training-only-opening-frequency-grid",
        "period": "2021-01-01/2023-12-31", "development_or_consumed_loaded": False,
        "event_rows": len(events), "calendar_sessions": len(calendar),
        "parameter_cells_completed": len(records),
        "retained_cells": sum(bool(item["retention_floor_passed"]) for item in records),
        "market_thresholds": market_thresholds,
        "elapsed_seconds": time.monotonic() - started,
        "records_by_training_rank": records,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp.json")
    temporary.write_text(json.dumps(result, indent=2) + "\n", "utf-8")
    temporary.replace(output)
    print(json.dumps({key: result[key] for key in ("status", "parameter_cells_completed", "retained_cells", "elapsed_seconds")}, indent=2))


if __name__ == "__main__":
    main()
