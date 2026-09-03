from __future__ import annotations

import json
import sys
from itertools import pairwise
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v13009_v13108_independent_sleeve_alpha as campaign


def test_v13009_campaign_is_frozen_before_scan() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v13009_v13108_independent_sleeve_alpha/proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == campaign.FIRST_VERSION == 13009
    assert proposal["last_version"] == campaign.LAST_VERSION == 13108
    assert all(
        all(left[1] <= right[0] for left, right in pairwise(group))
        for group in campaign.WINDOW_TRIPLES
    )


def test_execution_and_activation_contract() -> None:
    campaign._configure()
    assert tuple(campaign.base.ASSETS) == (3, 4)
    assert campaign.base.TOP_K == (1,)
    assert campaign.base._threshold is campaign._threshold
    assert campaign.base.MECHANISM == "independently_activated_triple_window_residual_alpha"
