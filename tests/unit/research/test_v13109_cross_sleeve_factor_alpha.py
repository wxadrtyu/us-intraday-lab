from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v13109_v13208_cross_sleeve_factor_alpha as campaign


def test_v13109_campaign_is_frozen_before_scan() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v13109_v13208_cross_sleeve_factor_alpha/proposal.json"
        ).read_text(encoding="utf-8")
    )
    combinations = {
        campaign._family_triple(first, variant)
        for first in campaign.FAMILIES
        for variant in campaign.VARIANTS
    }
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == campaign.FIRST_VERSION == 13109
    assert proposal["last_version"] == campaign.LAST_VERSION == 13208
    assert len(combinations) == 100


def test_execution_remains_joint_gated_and_non_overlapping() -> None:
    campaign._configure()
    assert tuple(campaign.base.ASSETS) == (3, 4)
    assert campaign.base.TOP_K == (1,)
    assert campaign.WINDOWS == ((2, 23), (23, 47), (47, 77))
    assert campaign.base.MECHANISM == "joint_gated_cross_sleeve_factor_alpha"
