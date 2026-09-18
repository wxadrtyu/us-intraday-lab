"""Frozen SEC fundamental-filing training feasibility diagnostic."""

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

DIAGNOSTIC_ID = "sec-fundamental-filing-training-feasibility-v2"
FAMILIES = (
    "revenue_acceleration",
    "gross_margin_expansion",
    "operating_margin_expansion",
    "cash_asset_improvement",
    "deleveraging",
)
FAMILY_FEATURES = {
    family: (feature, "continuation")
    for family, feature in zip(
        FAMILIES,
        (
            "revenue_growth_acceleration",
            "gross_margin_expansion",
            "operating_margin_expansion",
            "cash_asset_improvement",
            "deleveraging",
        ),
        strict=True,
    )
}


def coverage_gate(features: pd.DataFrame) -> dict[str, object]:
    """Fail closed unless issuer and feature-bearing filing floors are met."""
    required = {"symbol", "accession", "sec_feature_bearing"}
    if missing := required.difference(features.columns):
        raise ValueError(f"SEC_COVERAGE_COLUMNS_MISSING:{sorted(missing)}")
    bearing = features.loc[
        features["accession"].notna()
        & features["sec_feature_bearing"].fillna(False).astype(bool),
        ["symbol", "accession"],
    ].drop_duplicates()
    counts = bearing.groupby("symbol", observed=True).size()
    qualified_issuers = int(counts.ge(4).sum())
    feature_bearing_events = len(bearing)
    return {
        "passed": bool(qualified_issuers >= 300 and feature_bearing_events >= 1200),
        "qualified_issuers": qualified_issuers,
        "feature_bearing_issuer_floor": 300,
        "feature_bearing_events": feature_bearing_events,
        "feature_bearing_event_floor": 1200,
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
        raise AssertionError("SEC_FILING_DIAGNOSTIC_GRID_INVALID")
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
    event_sha256 = _sha256(events_path)
    feature_sha256 = _sha256(features_path)
    if event_sha256 != expected_event_sha256 or feature_sha256 != expected_feature_sha256:
        raise RuntimeError("SEC_FILING_DIAGNOSTIC_INPUT_HASH_MISMATCH")
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
            "decision": "ABANDON_SEC_FUNDAMENTAL_FILINGS_COVERAGE_GATE",
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
        proceed_decision="ACQUIRE_DEVELOPMENT_SEC_FUNDAMENTAL_FILINGS",
        abandon_decision="ABANDON_SEC_FUNDAMENTAL_FILINGS_NO_VERSION_CREATED",
    )
    return cells, {**summary, **gate}
