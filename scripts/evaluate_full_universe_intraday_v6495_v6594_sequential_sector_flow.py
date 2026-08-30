"""v6495-v6594: sequential non-overlapping sector-flow sleeves."""

from __future__ import annotations

import evaluate_full_universe_intraday_v6070_v6169_sequential_sector_flow as campaign

FIRST_VERSION = 6495
LAST_VERSION = 6594
PRIOR_COMPARISON_CELLS = 255_355


def _configure():
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS


if __name__ == "__main__":
    _configure()
    campaign.main()
