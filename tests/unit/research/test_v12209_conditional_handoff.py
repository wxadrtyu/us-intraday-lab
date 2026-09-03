from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v12209_v12308_conditional_handoff as campaign


def test_v12209_campaign_is_frozen_before_scan() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v12209_v12308_conditional_handoff/proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == campaign.FIRST_VERSION == 12209
    assert proposal["last_version"] == campaign.LAST_VERSION == 12308
    assert len(campaign.FACTOR_SETS) * len(campaign.SCHEDULES) == 100
    assert proposal["planned_parameter_cells"] == 600


def test_handoff_clocks_are_strictly_nonoverlapping() -> None:
    assert all(decision < handoff < final for decision, handoff, final in campaign.HANDOFF_SCHEDULES)
    assert len(set(campaign.HANDOFF_SCHEDULES)) == 10
    campaign._configure()
    assert campaign.base.DEFINITION_EXTRA is campaign._definition_extra
