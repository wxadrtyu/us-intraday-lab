from __future__ import annotations

import evaluate_full_universe_intraday_v9098_v9102_dual_soft_veto_merge as subject
import numpy as np


def test_dual_soft_veto_merge_contract():
    assert subject.FIRST_VERSION == 9098
    assert subject.LAST_VERSION == 9102
    assert subject.UNSTABLE_WEIGHTS == (0.30, 0.40, 0.50, 0.60, 0.70)
    assert subject.PRIMARY_WEIGHT == 0.50
    assert subject.PRIOR_COMPARISON_CELLS == 257_977


def test_blended_exposure_is_convex_and_gross_bounded():
    unstable = np.array([0.25, 1.0, 1.0])
    absorption = np.array([1.0, 0.25, 1.0])
    merged = subject._blend_exposure(unstable, absorption, 0.50)
    np.testing.assert_allclose(merged, [0.625, 0.625, 1.0])
    assert np.all((merged >= 0.0) & (merged <= 1.0))
