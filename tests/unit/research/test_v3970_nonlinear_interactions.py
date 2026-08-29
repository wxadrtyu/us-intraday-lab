from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v3970_v4069_nonlinear_interactions as subject


def test_campaign_has_one_hundred_versions() -> None:
    assert len(subject.specifications()) == 100


def test_quadratic_expansion_has_main_squares_and_pairs() -> None:
    values = np.ones((2, 2, 3))
    expanded = subject._expand(values)
    assert expanded.shape == (2, 2, 9)
    np.testing.assert_array_equal(expanded, 1.0)
