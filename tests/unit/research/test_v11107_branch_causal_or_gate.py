from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v11107_v11206_branch_causal_or_gate as campaign


def test_v11107_reserves_exactly_one_hundred_versions() -> None:
    assert campaign.LAST_VERSION - campaign.FIRST_VERSION + 1 == 100
    assert len(campaign.FACTOR_SETS) * len(campaign.QUANTILES) * len(campaign.ALPHAS) == 100


def test_v11107_keeps_branch_causal_route_clocks() -> None:
    campaign._configure()
    assert campaign.branch.EARLY_MINIMUM_ENTRY_BAR > 2
    assert campaign.branch.LATE_MINIMUM_ENTRY_BAR > 23
    assert all(spec[2] == "or" for spec in campaign.PAIR_SPECS.values())
