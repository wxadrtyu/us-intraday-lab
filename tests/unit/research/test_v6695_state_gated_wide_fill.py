from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v6695_v6794_state_gated_wide_fill as subject
import numpy as np


def _stream(values, active):
    values = np.asarray(values, dtype=float)
    active = np.asarray(active, dtype=bool)
    return v34.v12.ReturnStream(values, values * 0.1, active, active.astype(int))


def test_campaign_has_one_hundred_frozen_versions():
    assert subject.FIRST_VERSION == 6695
    assert subject.LAST_VERSION == 6794
    assert len(subject.specifications()) == 100
    assert np.isclose(subject.FILL_WEIGHTS.sum(), 1.0)


def test_state_gate_cannot_override_active_base():
    base = _stream([1.0, 0.0, 3.0], [True, False, True])
    fill = _stream([4.0, 5.0, 6.0], [True, True, True])
    combined = subject._disjoint_gated(base, fill, np.array([True, False, True]))
    np.testing.assert_allclose(combined.values, [1.0, 0.0, 3.0])
