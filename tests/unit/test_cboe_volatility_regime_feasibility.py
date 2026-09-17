from __future__ import annotations

import pandas as pd

from us_intraday_lab.cboe_volatility_regime_feasibility import (
    score_family,
    specifications,
)


def test_grid_has_exactly_400_unique_cells() -> None:
    grid = specifications()

    assert len(grid) == 400
    assert len(set(grid)) == 400


def test_stress_reversal_scores_loser_above_winner() -> None:
    frame = pd.DataFrame(
        {
            "session_date": ["2021-01-05", "2021-01-05"],
            "bar_idx": [2, 2],
            "session_return": [-0.02, 0.02],
            "vix9d_vix_z20": [1.5, 1.5],
        }
    )

    score = score_family(frame, "near_term_fear_inversion_reversal")

    assert score.iloc[0] > score.iloc[1]


def test_family_is_inactive_without_positive_regime_shock() -> None:
    frame = pd.DataFrame(
        {
            "session_date": ["2021-01-05"],
            "bar_idx": [2],
            "session_return": [-0.02],
            "vix9d_vix_z20": [-0.5],
        }
    )

    assert score_family(frame, "near_term_fear_inversion_reversal").isna().all()
