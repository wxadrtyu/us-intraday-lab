from __future__ import annotations

import validate_v10905_causal_bar5_and_native_null as subject


def test_native_null_preregistration() -> None:
    assert subject.VALIDATION_VERSION == 10905
    assert subject.REPETITIONS == 500
    assert subject.PERCENTILE == 0.95
    assert subject.SEED == 20260902
    assert subject.SAFE_SHIFT_MINIMUM >= 20
