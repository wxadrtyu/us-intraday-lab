"""v5995-v6094: nonlinear early-state routing before the modern sleeve."""

from __future__ import annotations

import evaluate_full_universe_intraday_v5870_v5969_nonlinear_meta_gate as campaign

FIRST_VERSION = 5995
LAST_VERSION = 6094
PRIOR_COMPARISON_CELLS = 254_855
GATE_DECISION = 2
FACTOR_SETS = {
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


def _configure():
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.GATE_DECISION = GATE_DECISION
    campaign.FACTOR_SETS = FACTOR_SETS

if __name__ == "__main__":
    _configure()
    campaign.main()
