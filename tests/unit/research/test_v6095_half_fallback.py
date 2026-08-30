from __future__ import annotations

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v5670_v5769_modern_quality_gate as linear
import evaluate_full_universe_intraday_v6095_v6194_half_fallback as subject
import numpy as np


def _stream(values):
    values = np.asarray(values, dtype=float)
    return v34.v12.ReturnStream(
        values, values * 0.2, np.ones(len(values), dtype=bool), np.ones(len(values), dtype=int)
    )


def test_half_fallback_scales_only_rejected_modern_days():
    parents = {
        linear.MODERN_PARENT: tuple(_stream([0.10, 0.20, 0.30]) for _ in range(3)),
        linear.TRANSFER_PARENT: tuple(_stream([0.40, 0.50, 0.60]) for _ in range(3)),
    }
    routed = subject._half_fallback_route(
        parents,
        np.array([True, True, False]),
        np.array([True, False, False]),
        np.array([False, False, True]),
    )
    np.testing.assert_allclose(routed[0].values, [0.10, 0.10, 0.60])
    np.testing.assert_allclose(routed[0].benchmark, [0.02, 0.02, 0.12])
    assert subject.FALLBACK_EXPOSURE <= 1.0
