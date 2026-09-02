from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v11508_v11607_v11098_sleeve_balance as campaign


def test_v11508_reserves_one_hundred_balances() -> None:
    assert campaign.LAST_VERSION - campaign.FIRST_VERSION + 1 == 100
    assert len(campaign.specifications()) == 100


def test_v11508_weights_are_conservative_and_nonzero() -> None:
    assert min(campaign.WEIGHTS) > 0.0
    assert max(campaign.WEIGHTS) < 1.0
