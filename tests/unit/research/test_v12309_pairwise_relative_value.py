from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v12309_v12408_pairwise_relative_value as campaign


def test_v12309_campaign_is_frozen_before_scan() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v12309_v12408_pairwise_relative_value/proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == campaign.FIRST_VERSION == 12309
    assert proposal["last_version"] == campaign.LAST_VERSION == 12408
    assert len(campaign.base.residual.FACTOR_SETS) * len(campaign.base.residual.SCHEDULES) == 100
    assert proposal["planned_parameter_cells"] == 1000


def test_pairwise_contract_is_long_only_single_winner() -> None:
    campaign._configure()
    assert tuple(campaign.base.ASSETS) == (3, 4)
    assert campaign.base.TOP_K == (1,)
    assert campaign.base.MECHANISM == "pairwise_tqqq_soxl_relative_value"
