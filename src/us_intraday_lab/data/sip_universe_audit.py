"""Fail-closed readiness audit for the Alpaca SIP full-market universe."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd


def _matched_volume_ratio(sip_daily: pd.DataFrame, iex_daily: pd.DataFrame) -> dict[str, Any]:
    required = {"symbol", "session_date", "volume"}
    if not required.issubset(sip_daily.columns) or not required.issubset(iex_daily.columns):
        return {"matched_rows": 0, "median_sip_to_iex_volume_ratio": None}
    sip = sip_daily.loc[:, ["symbol", "session_date", "volume"]].rename(
        columns={"volume": "sip_volume"}
    )
    iex = iex_daily.loc[:, ["symbol", "session_date", "volume"]].rename(
        columns={"volume": "iex_volume"}
    )
    matched = sip.merge(iex, on=["symbol", "session_date"], how="inner", validate="one_to_one")
    valid = matched.loc[matched["iex_volume"] > 0].copy()
    if valid.empty:
        return {"matched_rows": 0, "median_sip_to_iex_volume_ratio": None}
    ratio = valid["sip_volume"] / valid["iex_volume"]
    return {
        "matched_rows": len(valid),
        "median_sip_to_iex_volume_ratio": float(ratio.median()),
    }


def audit_sip_universe(
    *,
    expected_months: tuple[date, ...],
    observed_months: tuple[date, ...],
    sip_daily: pd.DataFrame,
    iex_daily: pd.DataFrame,
    independent_historical_master: bool,
    hashes_valid: bool,
    partial_partitions: int,
) -> dict[str, Any]:
    """Return an auditable gate; data sources are compared but never spliced."""
    missing_months = sorted(set(expected_months).difference(observed_months))
    reasons: list[str] = []
    if missing_months:
        reasons.append("EXPECTED_MONTH_MISSING")
    if not hashes_valid:
        reasons.append("PARTITION_HASH_INVALID")
    if partial_partitions:
        reasons.append("PARTIAL_PARTITION_PRESENT")
    if not independent_historical_master:
        reasons.append("INDEPENDENT_HISTORICAL_MASTER_MISSING")

    return {
        "schema_version": "1.0.0",
        "strategy_metrics_permitted": not reasons,
        "rejection_reasons": reasons,
        "expected_months": [month.isoformat() for month in expected_months],
        "observed_months": [month.isoformat() for month in observed_months],
        "missing_months": [month.isoformat() for month in missing_months],
        "sip_daily_rows": len(sip_daily),
        "iex_daily_rows": len(iex_daily),
        "hashes_valid": hashes_valid,
        "partial_partitions": partial_partitions,
        "survivorship": {
            "independent_historical_master": independent_historical_master,
            "current_asset_snapshot_is_point_in_time_history": False,
        },
        "source_bias": _matched_volume_ratio(sip_daily, iex_daily),
        "rows_spliced": 0,
        "missing_data_policy": "preserve_missing_no_fill_no_cash_substitution",
    }
