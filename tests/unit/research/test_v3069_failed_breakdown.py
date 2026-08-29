from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v3069_v3168_failed_breakdown as subject


def test_campaign_has_one_hundred_distinct_versions() -> None:
    subject.configure()
    assert len(subject.campaign.specifications()) == 100
    assert subject.campaign.FIRST_VERSION == 3069
    assert subject.campaign.LAST_VERSION == 3168
    assert subject.campaign.HISTORICAL_MIN_ANNUALIZED_RETURN == 0.15
    assert subject.campaign.REQUIRE_CONSUMED_2026Q1_GATE is True
