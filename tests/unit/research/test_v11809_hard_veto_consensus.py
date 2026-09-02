from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v11809_v11908_hard_veto_consensus as campaign


def test_v11809_campaign_is_frozen_before_scan() -> None:
    proposal_path = (
        Path(__file__).parents[3]
        / "research/proposals/full_universe_intraday_v11809_v11908_hard_veto_consensus/proposal.json"
    )
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == campaign.FIRST_VERSION == 11809
    assert proposal["last_version"] == campaign.LAST_VERSION == 11908
    assert proposal["planned_versions"] == 100
    assert len(campaign.FACTOR_SETS) * len(campaign.QUANTILES) * len(campaign.ALPHAS) == 100
    assert proposal["causal_execution"]["rejected_late_exposure"] == 0.0


def test_consensus_structures_are_genuinely_distinct() -> None:
    members = list(campaign.CONSENSUS_SPECS.values())
    assert len({tuple(item) for item in members}) == 5
    assert sorted(map(len, members)) == [3, 3, 3, 3, 4]
