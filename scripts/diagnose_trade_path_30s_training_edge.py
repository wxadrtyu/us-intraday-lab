"""Preregistered training-only fixed-30-second trade-path edge diagnostic."""

from __future__ import annotations

import argparse
import json
import math
import os
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

TRAIN_START = date(2021, 1, 1)
TRAIN_END = date(2023, 12, 31)
BARS = (2, 5, 11, 17, 23)
VOLUME_FLOORS = (0.0, 0.5, 0.75)
TOP_COUNTS = (1, 3, 5, 10)
EXITS = {1: "p2_open", 2: "p3_open", 4: "p5_open", 6: "p7_open"}
TRADE_WEIGHTS = (1.0, 0.75, 0.5)


def metrics(series: pd.Series) -> dict[str, float | int | dict[str, float]]:
    clean = series.fillna(0.0).astype(float)
    wealth = (1.0 + clean).cumprod()
    drawdown = wealth / wealth.cummax() - 1.0
    index = pd.DatetimeIndex(clean.index)
    year_returns = {
        str(year): float(np.prod(1.0 + clean.loc[index.year == year].to_numpy()) - 1.0)
        for year in sorted(set(index.year))
    }
    annualized = math.exp(float(np.log1p(clean.clip(lower=-0.999999)).sum()) * 252.0 / len(clean)) - 1.0
    volatility = float(clean.std(ddof=1))
    return {
        "annualized_return": annualized,
        "max_drawdown": float(-drawdown.min()),
        "information_ratio": float(clean.mean() / volatility * math.sqrt(252.0)) if volatility > 0 else 0.0,
        "positive_calendar_years": sum(value > 0 for value in year_returns.values()),
        "calendar_year_returns": year_returns,
    }


def percentile(frame: pd.DataFrame, column: str) -> pd.Series:
    return frame.groupby(["session_date", "bar_idx"], observed=True)[column].rank(pct=True).sub(0.5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument("--output", default="research/results/2026-09-07-trade-path-30s-training-edge.json")
    args = parser.parse_args()
    started = time.monotonic()
    cache_root = Path(args.data_root) / "research/cache"
    filters = [("session_date", ">=", TRAIN_START), ("session_date", "<=", TRAIN_END)]
    event_columns = [
        "symbol", "session_date", "bar_idx", "volume", "ret1", "ret3", "vwap_dev",
        "range_pos", "session_return", "directional_efficiency", "p1_open",
        "p2_open", "p3_open", "p5_open", "p7_open",
    ]
    trade_columns = [
        "symbol", "session_date", "bar_idx", "trade_available", "tick_volume_imbalance",
        "back_half_activity_share", "trade_path_return", "last_to_vwap", "trade_price_range",
        "largest_trade_share", "venue_count", "venue_concentration", "odd_lot_share",
    ]
    events = pd.read_parquet(cache_root / "v14309_v14408_events.parquet", columns=event_columns, filters=filters)
    trades = pd.read_parquet(cache_root / "us_market_event_trade_path_30s_v1.parquet", columns=trade_columns, filters=filters)
    for frame in (events, trades):
        frame["session_date"] = pd.to_datetime(frame["session_date"])
    events = events.loc[events["bar_idx"].isin(BARS)].merge(
        trades, on=["symbol", "session_date", "bar_idx"], how="left", validate="one_to_one"
    )
    events = events.loc[events["trade_available"].fillna(False)].copy()
    calendar = pd.DatetimeIndex(sorted(events["session_date"].unique()))

    rank_columns = [
        "volume", "ret1", "ret3", "vwap_dev", "range_pos", "session_return",
        "directional_efficiency", "tick_volume_imbalance", "back_half_activity_share",
        "trade_path_return", "last_to_vwap", "trade_price_range", "largest_trade_share",
        "venue_count", "venue_concentration", "odd_lot_share",
    ]
    ranks = {column: percentile(events, column) for column in rank_columns}
    events["volume_rank"] = ranks["volume"] + 0.5
    trade_scores = {
        "buy_pressure": ranks["tick_volume_imbalance"] + ranks["trade_path_return"] + ranks["last_to_vwap"] + ranks["back_half_activity_share"],
        "sell_exhaustion": -ranks["tick_volume_imbalance"] - ranks["trade_path_return"] - ranks["last_to_vwap"] - ranks["back_half_activity_share"],
        "path_continuation": ranks["trade_path_return"] + ranks["last_to_vwap"] + ranks["tick_volume_imbalance"],
        "path_reversal": -ranks["trade_path_return"] + ranks["last_to_vwap"] + ranks["tick_volume_imbalance"],
        "late_acceleration": ranks["back_half_activity_share"] + ranks["trade_path_return"] + ranks["last_to_vwap"],
        "late_absorption": ranks["back_half_activity_share"] - ranks["trade_path_return"] + ranks["tick_volume_imbalance"],
        "distributed_accumulation": ranks["tick_volume_imbalance"] + ranks["back_half_activity_share"] - ranks["largest_trade_share"] - ranks["venue_concentration"],
        "concentrated_impulse": ranks["trade_path_return"] + ranks["tick_volume_imbalance"] + ranks["largest_trade_share"] + ranks["venue_concentration"],
        "broad_venue_impulse": ranks["trade_path_return"] + ranks["tick_volume_imbalance"] + ranks["venue_count"] - ranks["venue_concentration"],
        "odd_lot_reversal": -ranks["trade_path_return"] - ranks["last_to_vwap"] + ranks["odd_lot_share"],
        "low_range_pressure": ranks["tick_volume_imbalance"] + ranks["last_to_vwap"] - ranks["trade_price_range"],
        "high_range_climax": -ranks["trade_path_return"] + ranks["trade_price_range"] + ranks["largest_trade_share"],
    }
    event_raw = {
        "bar_reversal": -ranks["ret1"] - ranks["ret3"] + ranks["volume"] - ranks["range_pos"],
        "bar_continuation": ranks["ret1"] + ranks["ret3"] + ranks["volume"] + ranks["directional_efficiency"],
        "vwap_reversion": -ranks["vwap_dev"] - ranks["ret1"] + ranks["volume"],
        "efficient_trend": ranks["session_return"] + ranks["directional_efficiency"] + ranks["volume"],
    }
    event_scores = {"none": pd.Series(0.0, index=events.index)}
    for name, score in event_raw.items():
        temporary = events[["session_date", "bar_idx"]].copy()
        temporary["score"] = score
        event_scores[name] = percentile(temporary, "score")
    for name, score in list(trade_scores.items()):
        temporary = events[["session_date", "bar_idx"]].copy()
        temporary["score"] = score
        trade_scores[name] = percentile(temporary, "score")

    records: list[dict[str, object]] = []
    for trade_model, trade_score in trade_scores.items():
        for state_model, state_score in event_scores.items():
            for trade_weight in TRADE_WEIGHTS:
                combined_score = trade_weight * trade_score + (1.0 - trade_weight) * state_score
                for bar_idx in BARS:
                    bar_mask = events["bar_idx"].eq(bar_idx)
                    for volume_floor in VOLUME_FLOORS:
                        eligible = events.loc[bar_mask & events["volume_rank"].ge(volume_floor)].copy()
                        eligible["score"] = combined_score.loc[eligible.index]
                        eligible = eligible.sort_values(
                            ["session_date", "score", "symbol"], ascending=[True, False, True], kind="stable"
                        )
                        eligible["selection_rank"] = eligible.groupby("session_date", observed=True).cumcount() + 1
                        for top_count in TOP_COUNTS:
                            selected = eligible.loc[eligible["selection_rank"].le(top_count)]
                            traded_days = pd.DatetimeIndex(selected["session_date"].drop_duplicates())
                            for holding_bars, exit_column in EXITS.items():
                                raw = (selected[exit_column] / selected["p1_open"] - 1.0).groupby(selected["session_date"]).mean()
                                daily = raw.reindex(calendar, fill_value=0.0)
                                daily.loc[traded_days] -= 0.0009
                                evaluated = metrics(daily)
                                record: dict[str, object] = {
                                    "trade_model": trade_model, "state_model": state_model,
                                    "trade_weight": trade_weight, "bar_idx": bar_idx,
                                    "volume_rank_floor": volume_floor, "top_count": top_count,
                                    "holding_bars": holding_bars, "signal_sessions": len(traded_days),
                                    **evaluated,
                                }
                                record["retention_floor_passed"] = bool(
                                    len(traded_days) >= 120
                                    and float(evaluated["annualized_return"]) >= 0.20
                                    and float(evaluated["information_ratio"]) >= 0.80
                                    and int(evaluated["positive_calendar_years"]) >= 2
                                )
                                records.append(record)

    records.sort(key=lambda item: (
        bool(item["retention_floor_passed"]), float(item["annualized_return"]),
        float(item["information_ratio"]), -float(item["max_drawdown"])
    ), reverse=True)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    full_results = output.with_suffix(".parquet")
    temporary_parquet = full_results.with_suffix(".tmp.parquet")
    pd.DataFrame(records).to_parquet(temporary_parquet, index=False, compression="zstd")
    os.replace(temporary_parquet, full_results)
    retained = [record for record in records if bool(record["retention_floor_passed"])]
    result = {
        "schema_version": "1.0.0", "status": "COMPLETE",
        "diagnostic_id": "trade-path-30s-training-edge-v1",
        "period": "2021-01-01/2023-12-31", "development_or_consumed_loaded": False,
        "event_rows": len(events), "calendar_sessions": len(calendar),
        "parameter_cells_completed": len(records), "retained_cells": len(retained),
        "elapsed_seconds": time.monotonic() - started,
        "full_results_path": str(full_results),
        "best_record": records[0] if records else None,
        "retained_records": retained,
        "top_200_by_training_rank": records[:200],
    }
    temporary_json = output.with_suffix(".tmp.json")
    temporary_json.write_text(json.dumps(result, indent=2) + "\n", "utf-8")
    os.replace(temporary_json, output)
    output.with_suffix(".md").write_text(
        "# Fixed-30-second trade-path training edge diagnostic\n\n"
        f"- Status: `{result['status']}`\n"
        f"- Training rows: {result['event_rows']:,}\n"
        f"- Cells: {result['parameter_cells_completed']:,}\n"
        f"- Retained: {result['retained_cells']:,}\n"
        f"- Elapsed seconds: {result['elapsed_seconds']:.2f}\n",
        "utf-8",
    )
    print(json.dumps({key: result[key] for key in (
        "status", "event_rows", "parameter_cells_completed", "retained_cells",
        "elapsed_seconds", "best_record"
    )}, indent=2), flush=True)


if __name__ == "__main__":
    main()
