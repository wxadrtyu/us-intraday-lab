from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v12409_v12508_beta_orthogonal_alpha as campaign


def test_v12409_campaign_is_frozen_before_scan() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v12409_v12508_beta_orthogonal_alpha/proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == campaign.FIRST_VERSION == 12409
    assert proposal["last_version"] == campaign.LAST_VERSION == 12508
    assert len(campaign.base.residual.FACTOR_SETS) * len(campaign.base.residual.SCHEDULES) == 100
    assert proposal["planned_parameter_cells"] == 1000
    assert proposal["fit_contract"]["beta_window"] == "train_2022_2023_only"


def test_execution_remains_long_only_single_asset() -> None:
    campaign._configure()
    assert tuple(campaign.base.ASSETS) == (3, 4)
    assert campaign.base.TOP_K == (1,)
    assert campaign.base.MECHANISM == "train_fixed_market_beta_orthogonal_alpha"
