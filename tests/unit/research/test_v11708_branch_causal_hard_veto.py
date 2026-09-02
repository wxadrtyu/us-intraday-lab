from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v11708_v11807_branch_causal_hard_veto as campaign


def test_v11708_preserves_grid_and_changes_only_rejected_exposure() -> None:
    campaign._configure()
    research = campaign.branch.boundary.logical.clock.parent.parent.sparse_veto.campaign
    opening = campaign.branch.boundary.logical.clock.parent.parent
    assert research.LAST_VERSION - research.FIRST_VERSION + 1 == 100
    assert len(research.FACTOR_SETS) * len(research.QUANTILES) * len(research.ALPHAS) == 100
    assert opening.LOW_EXPOSURE == 0.0
    assert campaign.branch.EARLY_MINIMUM_ENTRY_BAR > 2
    assert campaign.branch.LATE_MINIMUM_ENTRY_BAR > 23
