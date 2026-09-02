from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v11307_v11406_v11098_portfolio_vol as campaign


def test_v11307_reserves_exactly_one_hundred_overlays() -> None:
    assert campaign.LAST_VERSION - campaign.FIRST_VERSION + 1 == 100
    assert len(campaign.specifications()) == 100


def test_v11307_overlay_is_causal_and_bounded() -> None:
    assert min(campaign.LOOKBACKS) > 1
    assert min(campaign.FLOORS) > 0.0
    assert max(campaign.FLOORS) <= 1.0
