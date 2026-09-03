from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v13909_v14008_volume_clock_alpha as campaign


def test_v13909_campaign_is_frozen_before_scan() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v13909_v14008_volume_clock_alpha/proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == campaign.FIRST_VERSION == 13909
    assert proposal["last_version"] == campaign.LAST_VERSION == 14008
    assert len(campaign.PARTICIPATION_SETS) * len(campaign.SCHEDULES) == 100
    assert set(campaign.WINDOW_BY_SCHEDULE.values()) == {2, 3, 4, 5, 6}


def test_execution_remains_long_only_single_asset() -> None:
    campaign._configure()
    assert tuple(campaign.base.ASSETS) == (3, 4)
    assert campaign.base.TOP_K == (1,)
    assert campaign.base.MECHANISM == "causal_volume_clock_participation_shock_alpha"
