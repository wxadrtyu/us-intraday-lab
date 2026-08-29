from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v2866_v2965_one_reentry as reentry
import validate_full_universe_intraday_v3067_reentry_confirmation_null as subject


def test_candidate_wrapper_sets_frozen_recovery_threshold() -> None:
    assert subject.confirmation.recovery_threshold("anchor_only_reentry_0.0025") == 0.0025
    reentry.REENTRY_RECOVERY = 0.005
