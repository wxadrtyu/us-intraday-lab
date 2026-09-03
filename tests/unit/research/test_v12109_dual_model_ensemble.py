from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v12109_v12208_dual_model_ensemble as campaign


def test_v12109_campaign_is_frozen_before_scan() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v12109_v12208_dual_model_ensemble/proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == campaign.FIRST_VERSION == 12109
    assert proposal["last_version"] == campaign.LAST_VERSION == 12208
    assert len(campaign.PAIR_SPECS) * len(campaign.base.SCHEDULES) == 100
    assert proposal["planned_parameter_cells"] == 1000


def test_pairs_are_distinct_and_complementary() -> None:
    assert len(set(campaign.PAIR_SPECS.values())) == 10
    assert all(left != right for left, right in campaign.PAIR_SPECS.values())
    campaign._configure()
    assert campaign.base.TOP_K == (1,)
    assert tuple(campaign.base.ASSETS) == (3, 4)
