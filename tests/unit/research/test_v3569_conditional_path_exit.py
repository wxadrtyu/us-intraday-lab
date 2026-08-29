from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v3569_v3668_conditional_path_exit as subject


def test_campaign_has_one_hundred_distinct_versions() -> None:
    subject.configure()
    specifications = subject.campaign.specifications()
    assert len(specifications) == 100
    assert len(set(specifications)) == 100
    assert subject.campaign.PRIOR_COMPARISON_CELLS == 176_105


def test_two_stage_exit_is_close_confirmed_and_next_open() -> None:
    chosen = subject._chosen_exit(
        "two_stage_retracement",
        nominal_exit=53,
        first_exit=30,
        second_exit=36,
        first_return=np.array((-0.004, 0.010, 0.010)),
        second_return=np.array((0.000, 0.004, 0.009)),
    )
    np.testing.assert_array_equal(chosen, (30, 36, 53))
