from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v12909_v13008_four_window_alpha as campaign


def test_v12909_campaign_is_frozen_before_scan() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v12909_v13008_four_window_alpha/proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == campaign.FIRST_VERSION == 12909
    assert proposal["last_version"] == campaign.LAST_VERSION == 13008
    assert len(campaign.WINDOW_QUADRUPLES) == 10
    assert all(
        all(left[1] <= right[0] for left, right in zip(group, group[1:]))
        for group in campaign.WINDOW_QUADRUPLES
    )


def test_execution_remains_long_only_and_non_overlapping() -> None:
    campaign._configure()
    assert tuple(campaign.base.ASSETS) == (3, 4)
    assert campaign.base.TOP_K == (1,)
    assert campaign.base.MECHANISM == "non_overlapping_four_window_residual_alpha"
