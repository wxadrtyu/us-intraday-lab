from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v11408_v11507_midday_exhaustion_repair as campaign


def test_v11408_reserves_one_hundred_hypotheses() -> None:
    assert campaign.LAST_VERSION - campaign.FIRST_VERSION + 1 == 100
    assert len(campaign.FAMILIES) * len(campaign.SCHEDULES) * len(campaign.STATE_MODES) == 100


def test_v11408_is_causal_and_intraday_only() -> None:
    assert all(decision < exit_bar <= 77 for decision, exit_bar in campaign.SCHEDULES)
    assert min(decision for decision, _ in campaign.SCHEDULES) >= 23
