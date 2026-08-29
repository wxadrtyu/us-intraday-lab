from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v3269_v3368_overnight_dislocation as subject


def test_campaign_has_one_hundred_distinct_versions() -> None:
    subject.configure()
    specifications = subject.campaign.specifications()
    assert len(specifications) == 100
    assert len(set(specifications)) == 100
    assert subject.campaign.FIRST_VERSION == 3269
    assert subject.campaign.LAST_VERSION == 3368
    assert subject.campaign.PRIOR_COMPARISON_CELLS == 137_705
