from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v5770_v5869_dual_asset_allocation as subject


def test_campaign_has_one_hundred_frozen_versions() -> None:
    assert subject.FIRST_VERSION == 5770
    assert subject.LAST_VERSION == 5869
    assert len(subject.specifications()) == 100


def test_bounded_weights_sum_to_one() -> None:
    weights = subject._weights(np.array([[2.0, 1.0]]), 0.6, 0.1)
    assert np.isclose(weights.sum(), 1.0)
    assert weights.max() <= 0.6
