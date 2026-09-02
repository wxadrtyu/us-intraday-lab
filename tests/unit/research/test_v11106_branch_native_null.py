from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import validate_v10905_causal_bar5_and_native_null as base
import validate_v11106_branch_causal_native_null as validation


def test_native_null_preregistration_is_frozen() -> None:
    assert base.REPETITIONS == 500
    assert base.PERCENTILE == 0.95
    assert base.SAFE_SHIFT_MINIMUM == 20
    assert validation._BranchCampaignFacade.logical is validation.branch.boundary.logical
