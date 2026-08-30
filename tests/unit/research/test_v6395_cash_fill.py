from __future__ import annotations

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v4470_v4569_early_quality_gate as base
import evaluate_full_universe_intraday_v6395_v6494_cash_fill as subject
import numpy as np


def _stream(values):
    values = np.asarray(values, dtype=float)
    return v34.v12.ReturnStream(
        values, values * 0.1, np.ones(len(values), dtype=bool), np.ones(len(values), dtype=int)
    )


def test_cash_fill_is_used_only_when_both_primary_routes_abstain():
    subject._configure()
    parent_streams = {
        base.MODERN_PARENT: tuple(_stream([1.0, 1.0, 1.0]) for _ in range(3)),
        base.TRANSFER_PARENT: tuple(_stream([2.0, 2.0, 2.0]) for _ in range(3)),
        subject.FALLBACK_PARENT: tuple(_stream([3.0, 3.0, 3.0]) for _ in range(3)),
    }
    result = base._route(
        parent_streams,
        np.array([True, False, False]),
        np.array([False, True, False]),
    )
    np.testing.assert_allclose(result[0].values, [1.0, 2.0, 3.0])
    assert subject.FIRST_VERSION == 6395
