from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v7095_v7194_regime_gated_opening as subject
import numpy as np


def test_allowed_state_is_finite_and_above_threshold(monkeypatch):
    monkeypatch.setattr(
        subject.base.campaign.state,
        "_score",
        lambda cube, model: np.array([np.nan, -1.0, 0.0, 1.0]),
    )
    actual = subject._allowed_state(None, {"threshold": 0.0})
    np.testing.assert_array_equal(actual, [False, False, True, True])


def test_regime_gate_preregistration():
    assert subject.FIRST_VERSION == 7095
    assert subject.OPENING_STATE_FAMILY == "low_dispersion_trend"
    assert subject.OPENING_STATE_QUANTILE == 0.50
    assert subject.base.OPENING_SLOT[1] < 24
