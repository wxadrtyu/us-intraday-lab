from __future__ import annotations

import pandas as pd

from us_intraday_lab.cboe_volatility_regime_feasibility import score_family
from us_intraday_lab.sec_beneficial_ownership_feasibility import (
    FAMILY_FEATURES,
    coverage_gate,
    specifications,
)


def _inventory(issuers: int, filings: int) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [f"S{index:03d}" for index in range(issuers)],
            "sec_beneficial_cik": range(1, issuers + 1),
            "sec_beneficial_qualifying_filing_count": [filings] * issuers,
        }
    )


def _manifest(*, complete: bool = True) -> dict[str, object]:
    return {
        "status": "COMPLETE" if complete else "PARTIAL",
        "source_hashes_verified": complete,
        "training_years": [2021, 2022, 2023],
    }


def test_gate_requires_sources_300_issuers_7000_events_and_three_years() -> None:
    passed = coverage_gate(_inventory(300, 24), _manifest())
    issuer_failure = coverage_gate(_inventory(299, 24), _manifest())
    event_failure = coverage_gate(_inventory(300, 23), _manifest())
    source_failure = coverage_gate(_inventory(300, 24), _manifest(complete=False))

    assert passed["passed"] is True
    assert passed["qualified_issuers"] == 300
    assert passed["qualifying_symbol_filing_events"] == 7200
    assert issuer_failure["passed"] is False
    assert event_failure["passed"] is False
    assert source_failure["passed"] is False


def test_gate_counts_shared_cik_once_but_symbol_events_twice() -> None:
    frame = pd.DataFrame(
        {
            "symbol": ["AAA", "AAB"],
            "sec_beneficial_cik": [1, 1],
            "sec_beneficial_qualifying_filing_count": [20, 20],
        }
    )

    result = coverage_gate(frame, _manifest())

    assert result["qualified_issuers"] == 1
    assert result["qualifying_symbol_filing_events"] == 40


def test_grid_has_exactly_400_unique_cells() -> None:
    grid = specifications()

    assert len(grid) == 400
    assert len(set(grid)) == 400


def test_all_ownership_families_use_intraday_continuation() -> None:
    frame = pd.DataFrame(
        {
            "session_date": ["2022-08-01", "2022-08-01"],
            "bar_idx": [2, 2],
            "session_return": [0.02, -0.02],
            "sec_beneficial_sc13d": [1, 1],
        }
    )

    scores = score_family(frame, "original_sc13d", FAMILY_FEATURES)

    assert scores.iloc[0] > scores.iloc[1]
