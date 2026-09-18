from __future__ import annotations

import pandas as pd

from us_intraday_lab.cboe_volatility_regime_feasibility import score_family
from us_intraday_lab.sec_form4_insider_flow_feasibility import (
    FAMILY_FEATURES,
    coverage_gate,
    specifications,
)


def _inventory(issuers: int, filings: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [f"S{index:03d}" for index in range(issuers)],
            "sec_form4_qualifying_filing_count": [filings] * issuers,
            "sec_form4_qualifying_filing_years": ["2021|2022|2023"] * issuers,
        }
    )


def test_coverage_requires_300_issuers_and_3000_filings() -> None:
    passed = coverage_gate(_inventory(300, 10))
    issuer_failure = coverage_gate(_inventory(299, 11))
    event_failure = coverage_gate(_inventory(300, 9))

    assert passed["passed"] is True
    assert passed["qualified_issuers"] == 300
    assert passed["qualifying_filing_events"] == 3000
    assert passed["filing_years"] == [2021, 2022, 2023]
    assert issuer_failure["passed"] is False
    assert event_failure["passed"] is False


def test_coverage_inventory_must_be_consistent_per_symbol() -> None:
    frame = pd.concat([_inventory(300, 10), _inventory(1, 11)], ignore_index=True)

    try:
        coverage_gate(frame)
    except ValueError as error:
        assert str(error) == "SEC_FORM4_COVERAGE_COUNT_INCONSISTENT"
    else:
        raise AssertionError("inconsistent inventory must fail closed")


def test_grid_has_exactly_400_unique_cells() -> None:
    grid = specifications()

    assert len(grid) == 400
    assert len(set(grid)) == 400


def test_purchase_continuation_rewards_intraday_winner() -> None:
    frame = pd.DataFrame(
        {
            "session_date": ["2022-08-01", "2022-08-01"],
            "bar_idx": [2, 2],
            "session_return": [0.02, -0.02],
            "insider_purchase_notional": [0.9, 0.9],
        }
    )

    scores = score_family(frame, "purchase_notional", FAMILY_FEATURES)

    assert scores.iloc[0] > scores.iloc[1]
