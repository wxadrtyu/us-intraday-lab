from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import validate_v11407_v11098_portfolio_vol_native_null as validation


def test_v11407_freezes_large_maxt_native_null() -> None:
    assert validation.REPETITIONS == 500
    assert validation.PERCENTILE == 0.95
    assert validation.SAFE_SHIFT_MINIMUM >= 20
