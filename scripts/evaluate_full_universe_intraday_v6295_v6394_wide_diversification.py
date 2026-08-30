"""v6295-v6394: broad same-clock diversification over frozen v42 parents."""

from __future__ import annotations

import evaluate_full_universe_intraday_v4270_v4369_diversified_v42_ensemble as campaign

campaign.FIRST_VERSION = 6295
campaign.LAST_VERSION = 6394
campaign.PRIOR_COMPARISON_CELLS = 255_155
campaign.COUNTS = (8, 10, 12, 16, 20)
campaign.PENALTIES = (0.0, 0.25, 0.50, 0.75, 1.0)
campaign.WEIGHTINGS = ("equal", "inverse_train_volatility")
campaign.POOLS = ("development_frontier_100", "all_500")
campaign.MECHANISM = "wide_same_clock_train_stability_correlation_ensemble"


if __name__ == "__main__":
    campaign.main()
