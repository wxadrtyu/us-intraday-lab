from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v13609_v13708_state_acceleration_alpha as campaign


def test_v13609_campaign_is_frozen_before_scan() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v13609_v13708_state_acceleration_alpha/proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == campaign.FIRST_VERSION == 13609
    assert proposal["last_version"] == campaign.LAST_VERSION == 13708
    assert set(campaign.STEP_BY_SCHEDULE.values()) == {1, 2, 3, 4}
    assert all(2 * campaign.STEP_BY_SCHEDULE[s] <= s[0] for s in campaign.SCHEDULES)
    assert len(campaign.base.residual.FACTOR_SETS) * len(campaign.SCHEDULES) == 100


def test_execution_remains_long_only_single_asset() -> None:
    campaign._configure()
    assert tuple(campaign.base.ASSETS) == (3, 4)
    assert campaign.base.TOP_K == (1,)
    assert campaign.base.MECHANISM == "causal_intraday_factor_state_acceleration_alpha"
