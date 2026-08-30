from __future__ import annotations

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v7595_loss_veto_ensemble as subject
import numpy as np


def _stream(values, trades):
    values = np.asarray(values, dtype=float)
    return v34.v12.ReturnStream(
        values, values * 0.1, np.ones(len(values), dtype=bool), np.asarray(trades, dtype=int)
    )


def test_combine_preserves_unit_gross_weight_and_component_evidence():
    result = subject._combine((_stream([0.1, 0.2], [1, 1]), _stream([0.3, 0.4], [1, 0])))
    np.testing.assert_allclose(result.values, [0.2, 0.3])
    np.testing.assert_array_equal(result.component_trades, [2, 1])


def test_ensemble_preregistration():
    assert subject.VERSION == 7595
    assert len(subject.base.FACTOR_SETS) == 10
    assert subject.NULL_REPETITIONS == 500
