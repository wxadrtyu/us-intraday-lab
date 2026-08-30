from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v7195_v7294_opening_failed_breakdown as subject


def test_campaign_preregistration():
    assert subject.FIRST_VERSION == 7195
    assert subject.LAST_VERSION == 7294
    assert subject.OPENING_SLOT == (8, 23)
    assert subject.OPENING_SLOT[1] < 24
    assert subject.OPENING_FAMILY == "opening_reclaim"
    assert len(subject.OPENING_FACTORS) == 8
    assert subject.base.campaign.CORE_OVERSOLD_REPAIR
