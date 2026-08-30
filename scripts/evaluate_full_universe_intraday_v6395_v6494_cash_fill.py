"""v6395-v6494: fill routed cash states with a frozen development leader."""

from __future__ import annotations

import evaluate_full_universe_intraday_v4470_v4569_early_quality_gate as campaign

FIRST_VERSION = 6395
LAST_VERSION = 6494
PRIOR_COMPARISON_CELLS = 255_255
FALLBACK_PARENT = "lev-v42t-7c0af099b3c0f20b"


def _configure():
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.FALLBACK_PARENT = FALLBACK_PARENT
    campaign.MECHANISM = "bar2_transfer_gate_with_disjoint_cash_fill"


if __name__ == "__main__":
    _configure()
    campaign.main()
