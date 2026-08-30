"""v5995-v6094: nonlinear early-state routing before the modern sleeve."""

from __future__ import annotations

import evaluate_full_universe_intraday_v5870_v5969_nonlinear_meta_gate as campaign

campaign.FIRST_VERSION = 5995
campaign.LAST_VERSION = 6094
campaign.PRIOR_COMPARISON_CELLS = 254_855
campaign.GATE_DECISION = 2
campaign.FACTOR_SETS = {
    "early_trend_flow": (
        "current_return",
        "relative_return",
        "path_efficiency",
        "signed_volume_imbalance",
    ),
    "early_structure": ("current_return", "vwap_distance", "close_location", "session_range"),
    "early_cross_state": ("relative_return", "current_rank", "prior20_rank", "sector_breadth"),
    "early_reclaim": ("recent_return", "drawdown_from_high", "rebound_from_low", "close_location"),
    "early_balanced": (
        "current_return",
        "relative_return",
        "path_efficiency",
        "signed_volume_imbalance",
        "vwap_distance",
        "close_location",
        "prior20_return",
        "spy_volatility",
    ),
}

if __name__ == "__main__":
    campaign.main()
