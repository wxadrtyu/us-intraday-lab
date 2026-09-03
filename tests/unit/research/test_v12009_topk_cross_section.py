from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as campaign


def test_v12009_campaign_is_frozen_before_scan() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v12009_v12108_topk_cross_section/proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == campaign.FIRST_VERSION == 12009
    assert proposal["last_version"] == campaign.LAST_VERSION == 12108
    assert len(campaign.FACTOR_SETS) * len(campaign.SCHEDULES) == 100
    assert len(campaign.TOP_K) * len(campaign.QUANTILES) * len(campaign.TARGETS) == 24
    assert proposal["planned_parameter_cells"] == 2400
    assert proposal["mandatory_global_gate"] == "cumulative_bonferroni_p_below_0.05"


def test_topk_universe_and_gross_contract() -> None:
    assert len(campaign.ASSETS) == 13
    assert max(campaign.TOP_K) <= len(campaign.ASSETS)
    assert all(k >= 2 for k in campaign.TOP_K)
