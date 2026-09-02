from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import validate_v11808_branch_causal_hard_veto_native_null as validation


def test_v11808_freezes_two_candidate_maxt_null() -> None:
    assert validation.native.REPETITIONS == 500
    assert validation.native.PERCENTILE == 0.95
    assert validation.native.SAFE_SHIFT_MINIMUM >= 20
