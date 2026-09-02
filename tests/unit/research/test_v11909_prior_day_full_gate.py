from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v11909_v12008_prior_day_full_gate as campaign


def test_v11909_campaign_is_frozen_and_has_100_distinct_versions() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v11909_v12008_prior_day_full_gate/proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == campaign.FIRST_VERSION == 11909
    assert proposal["last_version"] == campaign.LAST_VERSION == 12008
    assert len(campaign.GATE_SPECS) * len(campaign.QUANTILES) == 100
    assert len(set(campaign.GATE_SPECS.values())) == 20
    assert proposal["mandatory_global_gate"] == "cumulative_bonferroni_p_below_0.05"


def test_v11909_uses_literal_bonferroni_and_cash_gate() -> None:
    campaign._configure()
    evaluator = campaign.hard.branch.boundary.logical.clock.parent.parent.sparse_veto.campaign
    assert evaluator.EFFECTIVE_FIRST_VERSION > campaign.LAST_VERSION
    assert evaluator.STREAM_TRANSFORM is campaign._full_session_cash_gate
