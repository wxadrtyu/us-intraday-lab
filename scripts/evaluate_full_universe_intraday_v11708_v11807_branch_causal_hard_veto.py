"""Hard-cash quality veto over the branch-causal v11098 architecture."""

from __future__ import annotations

import evaluate_full_universe_intraday_v11006_v11105_branch_causal as branch

FIRST_VERSION = 11708
LAST_VERSION = 11807
PRIOR_COMPARISON_CELLS = 311_883


def _configure() -> None:
    branch._configure()
    opening = branch.boundary.logical.clock.parent.parent
    campaign = opening.sparse_veto.campaign
    opening.LOW_EXPOSURE = 0.0
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.MECHANISM = "branch_causal_hard_cash_quality_veto"


if __name__ == "__main__":
    _configure()
    branch.boundary.logical.clock.parent.parent.sparse_veto.campaign.main()
