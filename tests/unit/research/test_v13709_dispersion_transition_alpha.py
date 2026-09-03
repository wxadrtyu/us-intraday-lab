from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v13709_v13808_dispersion_transition_alpha as campaign


def test_v13709_campaign_is_frozen_before_scan() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v13709_v13808_dispersion_transition_alpha/proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == campaign.FIRST_VERSION == 13709
    assert proposal["last_version"] == campaign.LAST_VERSION == 13808
    assert set(campaign.LAG_BY_SCHEDULE.values()) == {2, 3, 4, 5, 6}
    assert len(campaign.base.residual.FACTOR_SETS) * len(campaign.SCHEDULES) == 100


def test_panel_rank_is_centered_and_missing_safe() -> None:
    values = np.asarray([[3.0, 1.0, 2.0], [np.nan, 2.0, 1.0]])
    ranks = campaign._panel_rank(values)
    assert tuple(ranks[0]) == (0.5, -0.5, 0.0)
    assert np.isnan(ranks[1, 0])


def test_execution_remains_long_only_single_asset() -> None:
    campaign._configure()
    assert tuple(campaign.base.ASSETS) == (3, 4)
    assert campaign.base.TOP_K == (1,)
    assert campaign.base.MECHANISM == "causal_cross_sectional_dispersion_transition_alpha"
