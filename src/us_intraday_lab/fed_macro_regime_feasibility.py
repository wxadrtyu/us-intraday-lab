"""Frozen Federal Reserve macro-regime training feasibility wrapper."""

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
    "curve_inversion_stress_reversal",
    "long_rate_shock_continuation",
    "real_yield_shock_continuation",
    "breakeven_inflation_shock_continuation",
    "broad_dollar_shock_continuation",
)
FAMILY_FEATURES = {
    "curve_inversion_stress_reversal": ("curve_inversion_stress_z20", "reversal"),
    "long_rate_shock_continuation": ("dgs10_change_1", "continuation"),
    "real_yield_shock_continuation": ("dfii10_change_1", "continuation"),
    "breakeven_inflation_shock_continuation": ("t10yie_change_1", "continuation"),
    "broad_dollar_shock_continuation": ("dtwexbgs_change_1", "continuation"),
}


def specifications() -> tuple[Specification, ...]:
    result = tuple(
        Specification(family, decision, holding, top_count)
        for family in FAMILIES for decision in DECISION_BARS
        for holding in HOLDING_BARS for top_count in TOP_COUNTS
    )
    if len(result) != 400 or len(set(result)) != 400:
        raise AssertionError("FED_MACRO_DIAGNOSTIC_GRID_INVALID")
    return result


def run_diagnostic(
    *, events_path: Path, features_path: Path,
    expected_event_sha256: str, expected_feature_sha256: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    return run_configured_diagnostic(
        events_path=events_path, features_path=features_path,
        expected_event_sha256=expected_event_sha256,
        expected_feature_sha256=expected_feature_sha256,
        families=FAMILIES, family_features=FAMILY_FEATURES,
        diagnostic_id="fed-macro-regime-training-feasibility-v1",
        proceed_decision="ACQUIRE_DEVELOPMENT_FED_MACRO_REGIME",
        abandon_decision="ABANDON_FED_MACRO_REGIME_NO_VERSION_CREATED",
    )
