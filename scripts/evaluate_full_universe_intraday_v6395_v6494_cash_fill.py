"""v6395-v6494: fill routed cash states with a frozen development leader."""

from __future__ import annotations

import evaluate_full_universe_intraday_v4470_v4569_early_quality_gate as campaign

campaign.FIRST_VERSION = 6395
campaign.LAST_VERSION = 6494
campaign.PRIOR_COMPARISON_CELLS = 255_255
campaign.FALLBACK_PARENT = "lev-v42t-7c0af099b3c0f20b"
campaign.MECHANISM = "bar2_transfer_gate_with_disjoint_cash_fill"


if __name__ == "__main__":
    campaign.main()
