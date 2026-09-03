from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v14009_v14108_lead_lag_alpha as campaign


def test_v14009_campaign_is_frozen_before_scan() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v14009_v14108_lead_lag_alpha/proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == campaign.FIRST_VERSION == 14009
    assert proposal["last_version"] == campaign.LAST_VERSION == 14108
    assert len(campaign.RELATIONSHIPS) * len(campaign.SCHEDULES) == 100
    assert {item[1] for item in campaign.RELATIONSHIPS.values()} == {1, 2, 3}


def test_execution_remains_long_only_single_asset() -> None:
    campaign._configure()
    assert tuple(campaign.base.ASSETS) == (3, 4)
    assert campaign.base.TOP_K == (1,)
    assert campaign.base.MECHANISM == "causal_cross_asset_correlation_break_lead_lag_alpha"
