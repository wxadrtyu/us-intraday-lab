from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v12509_v12608_regime_interaction_alpha as campaign


def test_v12509_campaign_is_frozen_before_scan() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v12509_v12608_regime_interaction_alpha/proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == campaign.FIRST_VERSION == 12509
    assert proposal["last_version"] == campaign.LAST_VERSION == 12608
    assert proposal["planned_parameter_cells"] == 1000
    assert proposal["fit_contract"]["thresholds_frozen_outside_training"] is True


def test_execution_remains_long_only_single_asset() -> None:
    campaign._configure()
    assert tuple(campaign.base.ASSETS) == (3, 4)
    assert campaign.base.TOP_K == (1,)
    assert campaign.base.MECHANISM == "train_fixed_market_state_interaction_alpha"
