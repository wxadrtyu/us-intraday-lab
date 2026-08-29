from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v3369_v3468_multiday_exhaustion as subject


def test_campaign_has_one_hundred_distinct_versions() -> None:
    subject.configure()
    specifications = subject.campaign.specifications()
    assert len(specifications) == 100
    assert len(set(specifications)) == 100
    assert subject.campaign.PRIOR_COMPARISON_CELLS == 150_505


def test_rolling_compound_uses_only_available_prior_returns() -> None:
    values = np.array([[np.nan], [0.10], [-0.05], [0.02], [0.03]])
    result = subject._rolling_compound(values, 3)
    assert np.isnan(result[2, 0])
    np.testing.assert_allclose(result[3, 0], (1.10 * 0.95 * 1.02) - 1.0)
