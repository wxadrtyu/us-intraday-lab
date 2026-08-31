from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import evaluate_full_universe_intraday_v7695_v7794_midday_cross_sectional as subject


def test_midday_cross_sectional_preregistration():
    subject._configure()
    assert subject.FIRST_VERSION == 7695
    assert subject.LAST_VERSION == 7794
    assert subject.PRIOR_COMPARISON_CELLS == 256_555
    assert len(subject.FAMILIES) == 10
    assert len(subject.campaign.specifications()) == 100
    assert all(decision < exit_bar for decision, exit_bar in subject.SCHEDULES)
    assert subject.campaign._record is subject._record
