from __future__ import annotations

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v6995_v7094_opening_late_ensemble as subject
import numpy as np


def test_opening_and_late_intervals_are_nonoverlapping():
    assert subject.OPENING_SLOT[1] < 24
    assert subject.FIRST_VERSION == 6995
    assert len(subject.state_interactions.STATE_FAMILIES) == 10


def test_masked_stream_is_cash_outside_state():
    stream = v34.v12.ReturnStream(
        np.array([0.1, 0.2]),
        np.array([0.01, 0.02]),
        np.array([True, True]),
        np.array([1, 1]),
    )
    result = subject._masked(stream, np.array([True, False]))
    np.testing.assert_allclose(result.values, [0.1, 0.0])
    np.testing.assert_array_equal(result.component_trades, [1, 0])
