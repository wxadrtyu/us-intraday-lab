from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v3169_v3268_leverage_residual as subject


def test_campaign_has_one_hundred_distinct_versions() -> None:
    subject.configure()
    assert len(subject.campaign.specifications()) == 100
    assert subject.campaign.FIRST_VERSION == 3169
    assert subject.campaign.LAST_VERSION == 3268
    assert subject.campaign.PRIOR_COMPARISON_CELLS == 124_905


def test_residual_acceleration_is_recent_minus_earlier(monkeypatch) -> None:
    cube = object.__new__(subject.ResidualCube)
    cube.bar_return = np.zeros((1, 5, 11), dtype=float)
    for asset in subject.LEVERAGED:
        cube.bar_return[0, :, asset] = (0.01, 0.02, 0.04, 0.05, 0.06)
    base = {
        "current_return": np.zeros((1, 11), dtype=float),
        "recent_return": np.zeros((1, 11), dtype=float),
    }
    monkeypatch.setattr(subject.path.IntradayPathCube, "factors", lambda self, decision: base)

    factors = cube.factors(4)

    np.testing.assert_allclose(factors["residual_acceleration"][0, subject.LEVERAGED], 0.0325)
