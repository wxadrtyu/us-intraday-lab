"""Preregistered training-only fixed-five-second quote-path edge diagnostic."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import date
from pathlib import Path

import pandas as pd

from scripts.diagnose_trade_path_30s_training_edge import metrics, percentile

TRAIN_START = date(2021, 1, 1)
TRAIN_END = date(2023, 12, 31)
BARS = (2, 5, 11, 17, 23)
VOLUME_FLOORS = (0.0, 0.5, 0.75)
TOP_COUNTS = (1, 3, 5, 10)
EXITS = {1: "p2_open", 2: "p3_open", 4: "p5_open", 6: "p7_open"}
QUOTE_WEIGHTS = (1.0, 0.75, 0.5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument("--output", default="research/results/2026-09-08-quote-path-5s-training-edge.json")
    args = parser.parse_args()
    started = time.monotonic()
    cache_root = Path(args.data_root) / "research/cache"
    filters = [("session_date", ">=", TRAIN_START), ("session_date", "<=", TRAIN_END)]
    event_columns = [
        "symbol", "session_date", "bar_idx", "volume", "ret1", "ret3", "vwap_dev",
        "range_pos", "session_return", "directional_efficiency", "p1_open",
        "p2_open", "p3_open", "p5_open", "p7_open",
    ]
    quote_columns = [
        "symbol", "session_date", "bar_idx", "quote_available", "quotes_5s",
        "midpoint_return", "microprice_return", "midpoint_range", "mean_relative_spread",
        "last_relative_spread", "spread_change", "mean_size_imbalance",
        "last_size_imbalance", "size_imbalance_change", "back_half_update_share",
        "bid_price_pressure", "ask_price_pressure", "bid_size_pressure",
        "ask_size_pressure", "locked_or_crossed_share", "last_quote_age_ms",
    ]
    events = pd.read_parquet(cache_root / "v14309_v14408_events.parquet", columns=event_columns, filters=filters)
    quotes = pd.read_parquet(cache_root / "us_market_event_quote_path_5s_v1.parquet", columns=quote_columns, filters=filters)
    for frame in (events, quotes):
        frame["session_date"] = pd.to_datetime(frame["session_date"])
    events = events.loc[events["bar_idx"].isin(BARS)].merge(
        quotes, on=["symbol", "session_date", "bar_idx"], how="left", validate="one_to_one"
    )
    events = events.loc[events["quote_available"].fillna(False)].copy()
    calendar = pd.DatetimeIndex(sorted(events["session_date"].unique()))
    rank_columns = [
        "volume", "ret1", "ret3", "vwap_dev", "range_pos", "session_return",
        "directional_efficiency", "quotes_5s", "midpoint_return", "microprice_return",
        "midpoint_range", "mean_relative_spread", "last_relative_spread", "spread_change",
        "mean_size_imbalance", "last_size_imbalance", "size_imbalance_change",
        "back_half_update_share", "bid_price_pressure", "ask_price_pressure",
        "bid_size_pressure", "ask_size_pressure", "locked_or_crossed_share", "last_quote_age_ms",
    ]
    ranks = {column: percentile(events, column) for column in rank_columns}
    events["volume_rank"] = ranks["volume"] + 0.5
    quote_scores = {
        "bid_impulse": ranks["midpoint_return"] + ranks["microprice_return"] + ranks["bid_price_pressure"] + ranks["size_imbalance_change"],
        "sell_exhaustion": -ranks["midpoint_return"] - ranks["microprice_return"] + ranks["size_imbalance_change"] - ranks["spread_change"],
        "microprice_divergence": ranks["microprice_return"] - ranks["midpoint_return"] + ranks["last_size_imbalance"],
        "imbalance_accumulation": ranks["mean_size_imbalance"] + ranks["last_size_imbalance"] + ranks["size_imbalance_change"],
        "spread_compression": -ranks["spread_change"] - ranks["last_relative_spread"] + ranks["size_imbalance_change"],
        "late_quote_acceleration": ranks["back_half_update_share"] + ranks["midpoint_return"] + ranks["microprice_return"],
        "bid_replenishment": ranks["bid_size_pressure"] - ranks["ask_size_pressure"] + ranks["last_size_imbalance"],
        "ask_withdrawal": -ranks["ask_size_pressure"] + ranks["bid_price_pressure"] + ranks["microprice_return"],
        "liquidity_vacuum_continuation": ranks["spread_change"] + ranks["midpoint_return"] + ranks["microprice_return"] - ranks["quotes_5s"],
        "locked_pressure": ranks["locked_or_crossed_share"] + ranks["microprice_return"] + ranks["last_size_imbalance"],
        "calm_accumulation": -ranks["midpoint_range"] - ranks["last_relative_spread"] + ranks["last_size_imbalance"] + ranks["microprice_return"],
        "quote_churn_reversal": ranks["quotes_5s"] + ranks["back_half_update_share"] - ranks["midpoint_return"] + ranks["size_imbalance_change"],
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
    for name, score in list(quote_scores.items()):
        temporary = events[["session_date", "bar_idx"]].copy()
        temporary["score"] = score
        quote_scores[name] = percentile(temporary, "score")

    records: list[dict[str, object]] = []
    for quote_model, quote_score in quote_scores.items():
        for state_model, state_score in event_scores.items():
            for quote_weight in QUOTE_WEIGHTS:
                combined_score = quote_weight * quote_score + (1.0 - quote_weight) * state_score
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
                                    "quote_model": quote_model, "state_model": state_model,
                                    "quote_weight": quote_weight, "bar_idx": bar_idx,
                                    "volume_rank_floor": volume_floor, "top_count": top_count,
                                    "holding_bars": holding_bars, "signal_sessions": len(traded_days), **evaluated,
                                }
                                record["retention_floor_passed"] = bool(
                                    len(traded_days) >= 120 and float(evaluated["annualized_return"]) >= 0.20
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
        "diagnostic_id": "quote-path-5s-training-edge-v1",
        "period": "2021-01-01/2023-12-31", "development_or_consumed_loaded": False,
        "event_rows": len(events), "calendar_sessions": len(calendar),
        "parameter_cells_completed": len(records), "retained_cells": len(retained),
        "elapsed_seconds": time.monotonic() - started, "full_results_path": str(full_results),
        "best_record": records[0] if records else None, "retained_records": retained,
        "top_200_by_training_rank": records[:200],
    }
    temporary_json = output.with_suffix(".tmp.json")
    temporary_json.write_text(json.dumps(result, indent=2) + "\n", "utf-8")
    os.replace(temporary_json, output)
    output.with_suffix(".md").write_text(
        "# Fixed-five-second quote-path training edge diagnostic\n\n"
        f"- Status: `{result['status']}`\n- Training rows: {result['event_rows']:,}\n"
        f"- Cells: {result['parameter_cells_completed']:,}\n- Retained: {result['retained_cells']:,}\n"
        f"- Elapsed seconds: {result['elapsed_seconds']:.2f}\n", "utf-8",
    )
    print(json.dumps({key: result[key] for key in (
        "status", "event_rows", "parameter_cells_completed", "retained_cells", "elapsed_seconds", "best_record"
    )}, indent=2), flush=True)


if __name__ == "__main__":
    main()
