from __future__ import annotations

import pandas as pd

from us_intraday_lab.cboe_volatility_regime_feasibility import score_family
from us_intraday_lab.sec_8k_event_feasibility import (
    FAMILY_FEATURES,
    coverage_gate,
    specifications,
)


def _inventory(issuers: int, filings: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [f"S{index:03d}" for index in range(issuers)],
            "sec_8k_cik": range(1, issuers + 1),
            "sec_8k_categorized_filing_count": [filings] * issuers,
        }
    )


def _manifest(*, complete: bool = True) -> dict[str, object]:
    return {
        "status": "COMPLETE" if complete else "PARTIAL",
        "required_sources_complete": complete,
        "training_years": [2021, 2022, 2023],
    }


def test_coverage_requires_300_issuers_5000_events_and_complete_sources() -> None:
    passed = coverage_gate(_inventory(300, 17), _manifest())
    issuer_failure = coverage_gate(_inventory(299, 18), _manifest())
    event_failure = coverage_gate(_inventory(300, 16), _manifest())
    source_failure = coverage_gate(_inventory(300, 17), _manifest(complete=False))

    assert passed["passed"] is True
    assert passed["qualified_issuers"] == 300
    assert passed["categorized_symbol_filing_events"] == 5100
    assert issuer_failure["passed"] is False
    assert event_failure["passed"] is False
    assert source_failure["passed"] is False


def test_coverage_counts_shared_cik_once_but_symbol_events_twice() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["AAA", "AAB"],
            "sec_8k_cik": [1, 1],
            "sec_8k_categorized_filing_count": [20, 20],
        }
    )

    result = coverage_gate(frame, _manifest())

    assert result["qualified_issuers"] == 1
    assert result["categorized_symbol_filing_events"] == 40


def test_grid_has_exactly_400_unique_cells() -> None:
    grid = specifications()

    assert len(grid) == 400
    assert len(set(grid)) == 400


def test_director_change_family_uses_intraday_reversal() -> None:
    frame = pd.DataFrame(
        {
            "session_date": ["2022-08-01", "2022-08-01"],
            "bar_idx": [2, 2],
            "session_return": [0.02, -0.02],
            "sec_8k_director_officer_change": [1, 1],
        }
    )

    scores = score_family(frame, "director_officer_change", FAMILY_FEATURES)

    assert scores.iloc[1] > scores.iloc[0]
