"""Training-only gross-edge screen for trade filters on the opening climax sleeve."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument("--output", default="research/results/2026-09-07-training-only-trade-filter-diagnostic.json")
    args = parser.parse_args()
    root = Path(args.data_root) / "research/cache"
    events = pd.read_parquet(root / "v14309_v14408_events.parquet")
    trades = pd.read_parquet(root / "us_market_event_trade_features_1s_v1.parquet")
    for frame in (events, trades):
        frame["session_date"] = pd.to_datetime(frame["session_date"])
    events = events.loc[(events["session_date"] <= "2023-12-31") & events["bar_idx"].eq(2)].copy()
    events["volume_rank"] = events.groupby("session_date")["volume"].rank(pct=True)
    events = events.merge(trades.loc[trades["bar_idx"].eq(2)], on=["symbol", "session_date", "bar_idx"], how="left", validate="one_to_one")
    events["base_score"] = -events["ret1"] + events["volume_rank"] - events["range_pos"]
    base = events.loc[(events["ret1"] < -0.010) & (events["volume_rank"] >= 0.90) & (events["range_pos"] <= 0.25)].copy()
    valid = base["trade_available"].fillna(False)
    families = {
        "unfiltered": pd.Series(True, index=base.index),
        "valid_trade": valid,
        "positive_location": valid & base["trade_location_volume_imbalance"].gt(0),
        "negative_location": valid & base["trade_location_volume_imbalance"].lt(0),
        "balanced_location": valid & base["trade_location_volume_imbalance"].abs().le(0.25),
        "extreme_location": valid & base["trade_location_volume_imbalance"].abs().ge(0.50),
        "print_below_mid": valid & base["last_trade_edge_to_midpoint"].lt(0),
        "print_not_above_mid": valid & base["last_trade_edge_to_midpoint"].le(0),
        "print_above_mid": valid & base["last_trade_edge_to_midpoint"].gt(0),
        "print_below_mid_negative_location": valid & base["last_trade_edge_to_midpoint"].lt(0) & base["trade_location_volume_imbalance"].lt(0),
        "print_below_mid_positive_location": valid & base["last_trade_edge_to_midpoint"].lt(0) & base["trade_location_volume_imbalance"].gt(0),
        "distributed_prints": valid & base["largest_trade_share"].le(base.loc[valid, "largest_trade_share"].quantile(0.25)),
        "concentrated_prints": valid & base["largest_trade_share"].ge(base.loc[valid, "largest_trade_share"].quantile(0.75)),
        "low_odd_lot": valid & base["odd_lot_share"].le(base.loc[valid, "odd_lot_share"].quantile(0.25)),
        "high_odd_lot": valid & base["odd_lot_share"].ge(base.loc[valid, "odd_lot_share"].quantile(0.75)),
        "no_trade": ~valid,
    }
    exits = {1: "p2_open", 2: "p3_open", 4: "p5_open", 6: "p7_open"}
    records: list[dict[str, object]] = []
    for family, mask in families.items():
        eligible = base.loc[mask].sort_values(["session_date", "base_score", "symbol"], ascending=[True, False, True]).copy()
        eligible["rank"] = eligible.groupby("session_date").cumcount() + 1
        for top_count in (1, 2, 3, 5, 10):
            selected = eligible.loc[eligible["rank"] <= top_count]
            for holding, exit_column in exits.items():
                raw = selected[exit_column] / selected["p1_open"] - 1.0
                records.append({"family": family, "top_count": top_count, "holding_bars": holding, "events": len(selected), "sessions": int(selected["session_date"].nunique()), "gross_mean_bp": float(raw.mean() * 1e4), "gross_daily_bp": float(raw.groupby(selected["session_date"]).mean().mean() * 1e4)})
    records.sort(key=lambda item: float(str(item["gross_daily_bp"])), reverse=True)
    result = {"schema_version": "1.0.0", "status": "COMPLETE", "period": "2021-01-01/2023-12-31 training only", "development_or_consumed_loaded": False, "base_events": len(base), "records": records}
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", "utf-8")
    print(json.dumps(records[:10], indent=2))


if __name__ == "__main__":
    main()
