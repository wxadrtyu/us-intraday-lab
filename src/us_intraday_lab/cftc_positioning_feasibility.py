"""Frozen CFTC positioning training-feasibility wrapper."""

from __future__ import annotations

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

FAMILIES = (
    "spx_asset_manager_confirmation",
    "nasdaq_leveraged_crowding_reversal",
    "russell_institutional_divergence",
    "vix_leveraged_stress_reversal",
    "treasury_positioning_risk_confirmation",
)
FAMILY_FEATURES = {
    "spx_asset_manager_confirmation": ("spx_asset_mgr_z26", "continuation"),
    "nasdaq_leveraged_crowding_reversal": (
        "nasdaq_lev_money_z26",
        "reversal",
    ),
    "russell_institutional_divergence": (
        "russell_divergence_z26",
        "continuation",
    ),
    "vix_leveraged_stress_reversal": (
        "vix_lev_money_change_z26",
        "reversal",
    ),
    "treasury_positioning_risk_confirmation": (
        "treasury_asset_mgr_change_z26",
        "continuation",
    ),
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
        raise AssertionError("CFTC_POSITIONING_DIAGNOSTIC_GRID_INVALID")
    return result


def run_diagnostic(
    *,
    events_path: Path,
    features_path: Path,
    expected_event_sha256: str,
    expected_feature_sha256: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    return run_configured_diagnostic(
        events_path=events_path,
        features_path=features_path,
        expected_event_sha256=expected_event_sha256,
        expected_feature_sha256=expected_feature_sha256,
        families=FAMILIES,
        family_features=FAMILY_FEATURES,
        diagnostic_id="cftc-positioning-training-feasibility-v1",
        proceed_decision="ACQUIRE_DEVELOPMENT_CFTC_POSITIONING",
        abandon_decision="ABANDON_CFTC_POSITIONING_NO_VERSION_CREATED",
    )
