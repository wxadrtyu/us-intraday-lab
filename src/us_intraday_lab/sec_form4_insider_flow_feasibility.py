"""Frozen SEC Form 4 insider-flow training feasibility diagnostic."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from us_intraday_lab.cboe_volatility_regime_feasibility import (
    DECISION_BARS,
    HOLDING_BARS,
    TOP_COUNTS,
    Specification,
)
from us_intraday_lab.cboe_volatility_regime_feasibility import (
    run_diagnostic as run_configured_diagnostic,
)

DIAGNOSTIC_ID = "sec-form4-insider-flow-training-feasibility-v1"
FAMILIES = (
    "purchase_notional",
    "purchase_holding_fraction",
    "purchase_owner_cluster",
    "officer_director_purchase_reversal",
    "net_purchase_balance",
)
FAMILY_FEATURES = {
    "purchase_notional": ("insider_purchase_notional", "continuation"),
    "purchase_holding_fraction": (
        "insider_purchase_holding_fraction",
        "continuation",
    ),
    "purchase_owner_cluster": (
        "insider_purchase_owner_cluster",
        "continuation",
    ),
    "officer_director_purchase_reversal": (
        "insider_officer_director_purchase",
        "reversal",
    ),
    "net_purchase_balance": (
        "insider_net_purchase_balance",
        "continuation",
    ),
}


def coverage_gate(features: pd.DataFrame) -> dict[str, object]:
    """Evaluate the frozen raw issuer-filing inventory before event projection."""
    count_column = "sec_form4_qualifying_filing_count"
    years_column = "sec_form4_qualifying_filing_years"
    required = {"symbol", count_column, years_column}
    if missing := required.difference(features.columns):
        raise ValueError(f"SEC_FORM4_COVERAGE_COLUMNS_MISSING:{sorted(missing)}")
    counts_numeric = pd.to_numeric(features[count_column], errors="coerce")
    if counts_numeric.isna().any() or counts_numeric.lt(0).any():
        raise ValueError("SEC_FORM4_COVERAGE_COUNT_INVALID")
    inventory = features.assign(_count=counts_numeric).groupby(
        "symbol", observed=True
    )["_count"]
    if inventory.nunique().gt(1).any():
        raise ValueError("SEC_FORM4_COVERAGE_COUNT_INCONSISTENT")
    counts = inventory.max().astype("int64")
    year_values = set()
    for value in features[years_column].dropna().astype(str).unique():
        year_values.update(int(year) for year in value.split("|") if year)
    filing_years = sorted(year_values)
    qualified_issuers = int(counts.ge(3).sum())
    qualifying_events = int(counts.sum())
    return {
        "passed": bool(
            qualified_issuers >= 300
            and qualifying_events >= 3000
            and filing_years == [2021, 2022, 2023]
        ),
        "qualified_issuers": qualified_issuers,
        "qualified_issuer_floor": 300,
        "minimum_filings_per_issuer": 3,
        "qualifying_filing_events": qualifying_events,
        "qualifying_filing_event_floor": 3000,
        "filing_years": filing_years,
    }


def specifications() -> tuple[Specification, ...]:
    result = tuple(
        Specification(family, decision, holding, top_count)
        for family in FAMILIES
        for decision in DECISION_BARS
        for holding in HOLDING_BARS
        for top_count in TOP_COUNTS
    )
    if len(result) != 400 or len(set(result)) != 400:
        raise AssertionError("SEC_FORM4_DIAGNOSTIC_GRID_INVALID")
    return result


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_diagnostic(
    *,
    events_path: Path,
    features_path: Path,
    expected_event_sha256: str,
    expected_feature_sha256: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Run the coverage gate and configured cost/delay grid with exact hashes."""
    event_sha256 = _sha256(events_path)
    feature_sha256 = _sha256(features_path)
    if event_sha256 != expected_event_sha256 or feature_sha256 != expected_feature_sha256:
        raise RuntimeError("SEC_FORM4_DIAGNOSTIC_INPUT_HASH_MISMATCH")
    features = pd.read_parquet(features_path)
    gate = coverage_gate(features)
    if not gate["passed"]:
        return pd.DataFrame(), {
            "schema_version": "1.0.0",
            "status": "COMPLETE",
            "diagnostic_id": DIAGNOSTIC_ID,
            "period": "2021-01-01/2023-12-31",
            "event_sha256": event_sha256,
            "feature_sha256": feature_sha256,
            "event_rows": len(features),
            "covered_event_rows": int(
                features["coverage_reason"].eq("COVERED").sum()
            ),
            "calendar_sessions": int(features["session_date"].nunique()),
            "cells_completed": 0,
            "retained_cells": 0,
            "retained_families": [],
            "decision": "ABANDON_SEC_FORM4_INSIDER_FLOW_COVERAGE_GATE",
            "best_cell": None,
            **gate,
            "development_or_consumed_loaded": False,
            "strategy_versions_created": 0,
            "paper_activation": False,
            "order_route": "FORBIDDEN",
            "elapsed_seconds": 0.0,
        }
    cells, summary = run_configured_diagnostic(
        events_path=events_path,
        features_path=features_path,
        expected_event_sha256=expected_event_sha256,
        expected_feature_sha256=expected_feature_sha256,
        families=FAMILIES,
        family_features=FAMILY_FEATURES,
        diagnostic_id=DIAGNOSTIC_ID,
        proceed_decision="ACQUIRE_DEVELOPMENT_SEC_FORM4_INSIDER_FLOW",
        abandon_decision="ABANDON_SEC_FORM4_INSIDER_FLOW_NO_VERSION_CREATED",
    )
    return cells, {**summary, **gate}
