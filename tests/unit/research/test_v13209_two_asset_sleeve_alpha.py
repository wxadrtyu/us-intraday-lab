from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v13109_v13208_cross_sleeve_factor_alpha as prior
import evaluate_full_universe_intraday_v13209_v13308_two_asset_sleeve_alpha as campaign


def test_v13209_campaign_is_frozen_and_disjoint() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v13209_v13308_two_asset_sleeve_alpha/proposal.json"
        ).read_text(encoding="utf-8")
    )
    old = {
        prior._family_triple(first, variant)
        for first in campaign.FAMILIES
        for variant in campaign.VARIANTS
    }
    new = {
        campaign._family_triple(first, variant)
        for first in campaign.FAMILIES
        for variant in campaign.VARIANTS
    }
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == campaign.FIRST_VERSION == 13209
    assert proposal["last_version"] == campaign.LAST_VERSION == 13308
    assert len(new) == 100
    assert old.isdisjoint(new)


def test_execution_includes_bounded_two_asset_diversification() -> None:
    campaign._configure()
    assert tuple(campaign.base.ASSETS) == (3, 4)
    assert campaign.base.TOP_K == (1, 2)
    assert campaign.base.MECHANISM == "joint_gated_cross_sleeve_two_asset_alpha"
