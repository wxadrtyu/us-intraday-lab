from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v6595_v6694_disjoint_wide_cash_fill as subject
import numpy as np


def _stream(values, active):
    values = np.asarray(values, dtype=float)
    active = np.asarray(active, dtype=bool)
    return v34.v12.ReturnStream(values, values * 0.1, active, active.astype(int))


def test_campaign_has_one_hundred_frozen_versions():
    assert subject.FIRST_VERSION == 6595
    assert subject.LAST_VERSION == 6694
    assert len(subject.specifications()) == 100


def test_fill_is_used_only_when_base_is_cash():
    base = _stream([1.0, 0.0, 3.0], [True, False, True])
    fill = _stream([4.0, 5.0, 6.0], [True, True, True])
    combined = subject._disjoint(base, fill)
    np.testing.assert_allclose(combined.values, [1.0, 5.0, 3.0])
    np.testing.assert_array_equal(combined.component_trades, [1, 1, 1])
