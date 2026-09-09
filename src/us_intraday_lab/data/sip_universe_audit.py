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
    event_grid_coverage_ratio: float | None = None,
    expected_candidate_symbols: tuple[str, ...] | None = None,
    decision_symbols: tuple[str, ...] | None = None,
    expected_sessions: tuple[date, ...] | None = None,
    observed_sessions: tuple[date, ...] | None = None,
    decision_grid_complete: bool | None = None,
    universe_hash_valid: bool | None = None,
) -> dict[str, Any]:
    """Return an auditable gate; data sources are compared but never spliced."""
    missing_months = sorted(set(expected_months).difference(observed_months))
    daily_reasons: list[str] = []
    if not expected_months:
        daily_reasons.append("EXPECTED_MONTH_SET_EMPTY")
    if missing_months:
        daily_reasons.append("EXPECTED_MONTH_MISSING")
    if sip_daily.empty:
        daily_reasons.append("SIP_DAILY_EMPTY")
    if not hashes_valid:
        daily_reasons.append("PARTITION_HASH_INVALID")
    if partial_partitions:
        daily_reasons.append("PARTIAL_PARTITION_PRESENT")
    if not independent_historical_master:
        daily_reasons.append("INDEPENDENT_HISTORICAL_MASTER_MISSING")
    missing_symbols: list[str] = []
    if expected_candidate_symbols is not None:
        missing_symbols = sorted(set(expected_candidate_symbols).difference(decision_symbols or ()))
        if missing_symbols:
            daily_reasons.append("CANDIDATE_SYMBOL_DECISIONS_MISSING")
    missing_sessions: list[date] = []
    if expected_sessions is not None:
        missing_sessions = sorted(set(expected_sessions).difference(observed_sessions or ()))
        if missing_sessions:
            daily_reasons.append("EXPECTED_XNYS_SESSION_MISSING")
    if decision_grid_complete is not True:
        daily_reasons.append("CANDIDATE_MONTH_DECISION_GRID_NOT_VERIFIED")
    if universe_hash_valid is not True:
        daily_reasons.append("UNIVERSE_HASH_NOT_VERIFIED")
    reasons = list(daily_reasons)
    if event_grid_coverage_ratio is None:
        reasons.append("DECISION_EVENT_GRID_NOT_AUDITED")
    elif event_grid_coverage_ratio < 0.95:
        reasons.append("DECISION_EVENT_GRID_COVERAGE_BELOW_95_PERCENT")

    return {
        "schema_version": "1.0.0",
        "daily_universe_permitted": not daily_reasons,
        "strategy_metrics_permitted": not reasons,
        "rejection_reasons": reasons,
        "expected_months": [month.isoformat() for month in expected_months],
        "observed_months": [month.isoformat() for month in observed_months],
        "missing_months": [month.isoformat() for month in missing_months],
        "missing_candidate_symbol_count": len(missing_symbols),
        "missing_candidate_symbols": missing_symbols,
        "missing_session_count": len(missing_sessions),
        "missing_sessions": [session.isoformat() for session in missing_sessions],
        "decision_grid_complete": decision_grid_complete,
        "universe_hash_valid": universe_hash_valid,
        "sip_daily_rows": len(sip_daily),
        "iex_daily_rows": len(iex_daily),
        "hashes_valid": hashes_valid,
        "partial_partitions": partial_partitions,
        "event_grid_coverage_ratio": event_grid_coverage_ratio,
        "survivorship": {
            "independent_historical_master": independent_historical_master,
            "current_asset_snapshot_is_point_in_time_history": False,
        },
        "source_bias": _matched_volume_ratio(sip_daily, iex_daily),
        "rows_spliced": 0,
        "missing_data_policy": "preserve_missing_no_fill_no_cash_substitution",
    }
