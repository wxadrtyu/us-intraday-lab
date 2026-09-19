"""Frozen SEC beneficial-ownership training feasibility diagnostic."""

from __future__ import annotations

import hashlib
import json
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

DIAGNOSTIC_ID = "sec-beneficial-ownership-training-feasibility-v1"
FAMILIES = (
    "original_sc13d",
    "sc13d_amendment",
    "original_sc13g",
    "sc13g_amendment",
    "clustered_disclosure",
)
FAMILY_FEATURES = {
    "original_sc13d": ("sec_beneficial_sc13d", "continuation"),
    "sc13d_amendment": (
        "sec_beneficial_sc13d_amendment",
        "continuation",
    ),
    "original_sc13g": ("sec_beneficial_sc13g", "continuation"),
    "sc13g_amendment": (
        "sec_beneficial_sc13g_amendment",
        "continuation",
    ),
    "clustered_disclosure": (
        "sec_beneficial_clustered",
        "continuation",
    ),
}


def coverage_gate(
    features: pd.DataFrame, manifest: dict[str, object]
) -> dict[str, object]:
    """Apply source completeness, issuer, event, and training-year floors."""
    required = {
        "symbol",
        "sec_beneficial_cik",
        "sec_beneficial_qualifying_filing_count",
    }
    if missing := required.difference(features.columns):
        raise ValueError(
            f"SEC_BENEFICIAL_COVERAGE_COLUMNS_MISSING:{sorted(missing)}"
        )
    counts = pd.to_numeric(
        features["sec_beneficial_qualifying_filing_count"], errors="coerce"
    )
    if counts.isna().any() or counts.lt(0).any():
        raise ValueError("SEC_BENEFICIAL_COVERAGE_COUNT_INVALID")
    inventory = features.assign(_count=counts).groupby(
        ["symbol", "sec_beneficial_cik"], observed=True, dropna=True
    )["_count"]
    if inventory.nunique().gt(1).any():
        raise ValueError("SEC_BENEFICIAL_COVERAGE_COUNT_INCONSISTENT")
    symbol_counts = inventory.max().astype("int64")
    cik_counts = symbol_counts.groupby(level="sec_beneficial_cik").max()
    qualified_issuers = int(cik_counts.ge(3).sum())
    symbol_events = int(symbol_counts.sum())
    years = sorted(int(year) for year in manifest.get("training_years", []))
    sources_complete = bool(
        manifest.get("status") == "COMPLETE"
        and manifest.get("source_hashes_verified") is True
    )
    return {
        "passed": bool(
            sources_complete
            and qualified_issuers >= 300
            and symbol_events >= 7000
            and years == [2021, 2022, 2023]
        ),
        "required_sources_complete": sources_complete,
        "qualified_issuers": qualified_issuers,
        "qualified_issuer_floor": 300,
        "minimum_filings_per_issuer": 3,
        "qualifying_symbol_filing_events": symbol_events,
        "qualifying_symbol_filing_event_floor": 7000,
        "filing_years": years,
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
        raise AssertionError("SEC_BENEFICIAL_DIAGNOSTIC_GRID_INVALID")
    return result


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_diagnostic(
    *,
    events_path: Path,
    features_path: Path,
    manifest_path: Path,
    expected_event_sha256: str,
    expected_feature_sha256: str,
    expected_manifest_sha256: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Run the coverage gate then exactly 400 frozen cost/delay cells."""
    event_sha256 = _sha256(events_path)
    feature_sha256 = _sha256(features_path)
    manifest_sha256 = _sha256(manifest_path)
    if (
        event_sha256 != expected_event_sha256
        or feature_sha256 != expected_feature_sha256
        or manifest_sha256 != expected_manifest_sha256
    ):
        raise RuntimeError("SEC_BENEFICIAL_DIAGNOSTIC_INPUT_HASH_MISMATCH")
    features = pd.read_parquet(features_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    gate = coverage_gate(features, manifest)
    if not gate["passed"]:
        return pd.DataFrame(), {
            "schema_version": "1.0.0",
            "status": "COMPLETE",
            "diagnostic_id": DIAGNOSTIC_ID,
            "period": "2021-01-01/2023-12-31",
            "event_sha256": event_sha256,
            "feature_sha256": feature_sha256,
            "manifest_sha256": manifest_sha256,
            "event_rows": len(features),
            "covered_event_rows": int(
                features["coverage_reason"].eq("COVERED").sum()
            ),
            "calendar_sessions": int(features["session_date"].nunique()),
            "cells_completed": 0,
            "retained_cells": 0,
            "retained_families": [],
            "decision": "ABANDON_SEC_BENEFICIAL_OWNERSHIP_COVERAGE_GATE",
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
        proceed_decision="ACQUIRE_DEVELOPMENT_SEC_BENEFICIAL_OWNERSHIP",
        abandon_decision=(
            "ABANDON_SEC_BENEFICIAL_OWNERSHIP_NO_VERSION_CREATED"
        ),
    )
    return cells, {**summary, "manifest_sha256": manifest_sha256, **gate}
