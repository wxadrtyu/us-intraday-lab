from __future__ import annotations

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v6595_v6694_causal_vol_scaled_cash_fill as subject
import numpy as np


def test_causal_scaler_never_increases_gross():
    values = np.array([0.10, -0.10] * 15, dtype=float)
    stream = v34.v12.ReturnStream(
        values,
        values * 0.1,
        np.ones(len(values), dtype=bool),
        np.ones(len(values), dtype=int),
    )
    scaled = subject._scale((stream,))[0]
    assert np.all(np.abs(scaled.values) <= np.abs(stream.values) + 1e-12)
    assert subject.MINIMUM_EXPOSURE > 0
    assert subject.TARGET_VOLATILITY == 0.30
