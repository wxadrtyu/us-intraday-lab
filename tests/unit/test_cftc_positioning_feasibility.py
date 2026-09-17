import pandas as pd

from us_intraday_lab.cboe_volatility_regime_feasibility import score_family
from us_intraday_lab.cftc_positioning_feasibility import (
    FAMILY_FEATURES,
    specifications,
)


def test_grid_has_exactly_400_unique_cells() -> None:
    grid = specifications()

    assert len(grid) == 400
    assert len(set(grid)) == 400


def test_vix_stress_family_ranks_loser_above_winner() -> None:
    frame = pd.DataFrame(
        {
            "session_date": ["2022-06-16", "2022-06-16"],
            "bar_idx": [2, 2],
            "session_return": [-0.02, 0.02],
            "vix_lev_money_change_z26": [1.5, 1.5],
        }
    )

    scores = score_family(
        frame, "vix_leveraged_stress_reversal", FAMILY_FEATURES
    )

    assert scores.iloc[0] > scores.iloc[1]
