from __future__ import annotations

import pandas as pd

from us_intraday_lab.cboe_volatility_regime_feasibility import score_family
from us_intraday_lab.sec_fundamental_filing_feasibility import (
    FAMILY_FEATURES,
    coverage_gate,
    specifications,
)


def _feature_events(issuers: int, filings_each: int) -> pd.DataFrame:
    rows = []
    for issuer in range(issuers):
        for filing in range(filings_each):
            rows.append(
                {
                    "symbol": f"S{issuer:03d}",
                    "accession": f"A{issuer:03d}-{filing}",
                    "revenue_growth_acceleration": 0.8,
                    "gross_margin_expansion": pd.NA,
                    "operating_margin_expansion": pd.NA,
                    "cash_asset_improvement": pd.NA,
                    "deleveraging": pd.NA,
                }
            )
    return pd.DataFrame(rows)


def test_coverage_gate_requires_three_hundred_issuers_and_twelve_hundred_events() -> None:
    passed = coverage_gate(_feature_events(300, 4))
    issuer_failure = coverage_gate(_feature_events(299, 5))
    event_failure = coverage_gate(_feature_events(300, 3))

    assert passed["passed"] is True
    assert passed["qualified_issuers"] == 300
    assert passed["feature_bearing_issuer_floor"] == 300
    assert passed["feature_bearing_events"] == 1200
    assert issuer_failure["passed"] is False
    assert event_failure["passed"] is False


def test_grid_has_exactly_four_hundred_unique_cells() -> None:
    grid = specifications()

    assert len(grid) == 400
    assert len(set(grid)) == 400


def test_positive_revenue_change_ranks_intraday_winner_above_loser() -> None:
    frame = pd.DataFrame(
        {
            "session_date": ["2022-08-01", "2022-08-01"],
            "bar_idx": [2, 2],
            "session_return": [0.02, -0.02],
            "revenue_growth_acceleration": [0.9, 0.9],
        }
    )

    scores = score_family(frame, "revenue_acceleration", FAMILY_FEATURES)

    assert scores.iloc[0] > scores.iloc[1]
