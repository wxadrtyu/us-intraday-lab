from __future__ import annotations

import validate_v9097_soft_sparse_gap_native_null as subject


def test_native_null_contract():
    assert subject.VALIDATION_VERSION == 9097
    assert subject.REPETITIONS == 500
    assert subject.PERCENTILE == 0.95
    assert subject.SEED == 20260831
    assert subject.SAFE_SHIFT_MINIMUM == 20
