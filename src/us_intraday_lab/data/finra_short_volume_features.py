"""Causal training features from lagged FINRA daily short-sale flow."""

from __future__ import annotations

import numpy as np
import pandas as pd


def build_features(coverage: pd.DataFrame, daily_prices: pd.DataFrame) -> pd.DataFrame:
    """Attach rolling source-session features while preserving every event row."""
    required = {
        "symbol",
        "session_date",
        "bar_idx",
        "source_date",
        "coverage_reason",
        "short_volume",
        "short_exempt_volume",
        "total_volume",
        "short_ratio",
        "short_exempt_ratio",
    }
    if missing := required.difference(coverage.columns):
        raise ValueError(f"FINRA_FEATURE_COLUMNS_MISSING:{sorted(missing)}")
    result = coverage.copy()
    if result.duplicated(["symbol", "session_date", "bar_idx"]).any():
        raise ValueError("FINRA_FEATURE_EVENT_KEY_DUPLICATE")
    result["_event_order"] = range(len(result))
    covered = result.loc[
        result["coverage_reason"].eq("COVERED"),
        [
            "source_date",
            "symbol",
            "short_volume",
            "short_exempt_volume",
            "total_volume",
            "short_ratio",
            "short_exempt_ratio",
        ],
    ].drop_duplicates(["source_date", "symbol"])
    covered = covered.sort_values(["symbol", "source_date"]).reset_index(drop=True)
    grouped = covered.groupby("symbol", sort=False, observed=True)
    covered["log_total_volume"] = np.log1p(covered["total_volume"])
    covered["short_ratio_mean_5"] = grouped["short_ratio"].transform(
        lambda values: values.rolling(5, min_periods=5).mean()
    )
    covered["short_ratio_mean_20"] = grouped["short_ratio"].transform(
        lambda values: values.rolling(20, min_periods=10).mean()
    )
    standard_deviation = grouped["short_ratio"].transform(
        lambda values: values.rolling(20, min_periods=10).std(ddof=0)
    )
    covered["valid_short_ratio_observations_20"] = grouped[
        "short_ratio"
    ].transform(lambda values: values.rolling(20, min_periods=1).count())
    covered["short_ratio_z20"] = (
        (covered["short_ratio"] - covered["short_ratio_mean_20"])
        / standard_deviation.replace(0, np.nan)
    )
    covered["short_ratio_change_1"] = grouped["short_ratio"].diff()
    covered["short_ratio_cross_section_pct"] = covered.groupby(
        "source_date", observed=True
    )["short_ratio"].rank(method="average", pct=True)
    covered["short_ratio_change_cross_section_pct"] = covered.groupby(
        "source_date", observed=True
    )["short_ratio_change_1"].rank(method="average", pct=True)
    covered["total_volume_cross_section_pct"] = covered.groupby(
        "source_date", observed=True
    )["total_volume"].rank(method="average", pct=True)

    prices = daily_prices.loc[:, ["trade_date", "symbol", "close"]].copy()
    prices["trade_date"] = pd.to_datetime(prices["trade_date"]).dt.date
    if prices.duplicated(["trade_date", "symbol"]).any():
        raise ValueError("FINRA_DAILY_PRICE_KEY_DUPLICATE")
    prices = prices.sort_values(["symbol", "trade_date"])
    prices["source_return"] = prices.groupby("symbol", observed=True)["close"].pct_change(
        fill_method=None
    )
    covered = covered.merge(
        prices.loc[:, ["trade_date", "symbol", "source_return"]],
        how="left",
        left_on=["source_date", "symbol"],
        right_on=["trade_date", "symbol"],
        validate="one_to_one",
    ).drop(columns=["trade_date"])
    covered["short_flow_return_interaction"] = (
        covered["short_ratio_z20"] * covered["source_return"]
    )

    feature_columns = [
        "source_date",
        "symbol",
        "log_total_volume",
        "short_ratio_mean_5",
        "short_ratio_mean_20",
        "valid_short_ratio_observations_20",
        "short_ratio_z20",
        "short_ratio_change_1",
        "short_ratio_cross_section_pct",
        "short_ratio_change_cross_section_pct",
        "total_volume_cross_section_pct",
        "source_return",
        "short_flow_return_interaction",
    ]
    result = result.merge(
        covered.loc[:, feature_columns],
        how="left",
        on=["source_date", "symbol"],
        validate="many_to_one",
        sort=False,
    )
    result["valid_short_ratio_observations_20"] = result[
        "valid_short_ratio_observations_20"
    ].fillna(0).astype(int)
    return result.sort_values("_event_order").drop(columns=["_event_order"])
