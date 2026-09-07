"""Development-only cross-sectional diagnostics for audited SIP quote features."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", default=r"E:\us-intraday-lab-data\us-market")
    parser.add_argument(
        "--output", default="research/results/2026-09-07-sip-quote-state-diagnostics.json"
    )
    args = parser.parse_args()
    root = Path(args.data_root)
    events = pd.read_parquet(root / "research/cache/v14309_v14408_events.parquet")
    quotes = pd.read_parquet(root / "research/cache/us_market_event_quote_features_v1.parquet")
    events["session_date"] = pd.to_datetime(events["session_date"])
    quotes["session_date"] = pd.to_datetime(quotes["session_date"])
    quote_columns = [
        "symbol", "session_date", "bar_idx", "quote_available", "relative_spread",
        "size_imbalance", "quote_age_ms", "locked_or_crossed", "quotes_seen",
    ]
    frame = events.merge(
        quotes[quote_columns], on=["symbol", "session_date", "bar_idx"], how="inner",
        validate="one_to_one",
    )
    frame = frame.loc[
        frame["session_date"].between("2021-01-01", "2025-12-31")
        & frame["quote_available"].astype(bool)
        & frame["relative_spread"].between(0, 0.05)
        & ~frame["locked_or_crossed"].astype(bool)
    ].copy()
    exits = {1: "p2_open", 2: "p3_open", 4: "p5_open", 6: "p7_open"}
    for holding, column in exits.items():
        frame[f"fwd_{holding}"] = frame[column] / frame["p1_open"] - 1.0
    keys = ["session_date", "bar_idx"]
    features = {
        "spread": "relative_spread",
        "age": "quote_age_ms",
        "imbalance": "size_imbalance",
        "activity": "quotes_seen",
    }
    for name, column in features.items():
        rank = frame.groupby(keys, sort=False)[column].rank(pct=True, method="average")
        frame[f"{name}_quintile"] = np.minimum(5, np.ceil(rank * 5)).astype("int8")
    frame["period"] = np.where(
        frame["session_date"].le("2023-12-31"), "train_2021_2023", "dev_2024_2025"
    )
    frame["price_state"] = np.where(frame["ret1"] < 0, "down", "up")
    frame["vwap_state"] = np.where(frame["vwap_dev"] < 0, "below", "above")

    records: list[dict[str, object]] = []
    for feature in features:
        quintile = f"{feature}_quintile"
        for (period, bucket), subset in frame.groupby(["period", quintile], observed=True):
            for holding in exits:
                values = subset[f"fwd_{holding}"].dropna().to_numpy(dtype=float)
                records.append(
                    {
                        "section": "unconditional_quintile",
                        "period": period,
                        "feature": feature,
                        "bucket": int(bucket),
                        "holding_bars": holding,
                        "observations": len(values),
                        "mean_gross_bps": float(values.mean() * 10000),
                        "t_stat": float(values.mean() / (values.std(ddof=1) / np.sqrt(len(values)))),
                    }
                )
        extreme = frame.loc[frame[quintile].isin((1, 5))]
        for (period, price_state, vwap_state, bucket), subset in extreme.groupby(
            ["period", "price_state", "vwap_state", quintile], observed=True
        ):
            for holding in exits:
                values = subset[f"fwd_{holding}"].dropna().to_numpy(dtype=float)
                records.append(
                    {
                        "section": "conditional_extreme",
                        "period": period,
                        "feature": feature,
                        "bucket": int(bucket),
                        "price_state": price_state,
                        "vwap_state": vwap_state,
                        "holding_bars": holding,
                        "observations": len(values),
                        "mean_gross_bps": float(values.mean() * 10000),
                        "t_stat": float(values.mean() / (values.std(ddof=1) / np.sqrt(len(values)))),
                    }
                )
    result = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "selection_data_end": "2025-12-31",
        "consumed_2026_loaded": False,
        "rows": len(frame),
        "records": records,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    diagnostic = pd.DataFrame(records)
    unconditional = diagnostic.loc[diagnostic["section"].eq("unconditional_quintile")]
    pivot = unconditional.pivot_table(
        index=["feature", "bucket", "holding_bars"], columns="period",
        values="mean_gross_bps",
    ).dropna()
    consistent = pivot.loc[(np.sign(pivot.iloc[:, 0]) == np.sign(pivot.iloc[:, 1]))].copy()
    consistent["min_abs_bps"] = consistent.abs().min(axis=1)
    consistent = consistent.sort_values("min_abs_bps", ascending=False).head(12)
    output.with_suffix(".md").write_text(
        "# SIP quote-state development diagnostics\n\n"
        "2026 data was not loaded. Values below are mean gross event returns in basis points.\n\n"
        + consistent.to_markdown()
        + "\n",
        "utf-8",
    )
    print(json.dumps({"status": "COMPLETE", "rows": len(frame), "records": len(records)}))


if __name__ == "__main__":
    main()
