from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v11207_v11306_opening_dislocation as campaign


def test_v11207_reserves_one_hundred_distinct_hypotheses() -> None:
    assert campaign.LAST_VERSION - campaign.FIRST_VERSION + 1 == 100
    assert len(campaign.FAMILIES) * len(campaign.SCHEDULES) * len(campaign.STATE_MODES) == 100


def test_v11207_entry_is_after_every_frozen_decision() -> None:
    assert all(decision < exit_bar for decision, exit_bar in campaign.SCHEDULES)
    assert min(decision for decision, _ in campaign.SCHEDULES) >= 2
