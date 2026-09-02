"""Independent opening-dislocation continuation and repair campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v550_v649_state_gated_reversal as campaign
import evaluate_full_universe_intraday_v7695_v7794_midday_cross_sectional as strict

FIRST_VERSION = 11207
LAST_VERSION = 11306
PRIOR_COMPARISON_CELLS = 285_983
FAMILIES = (
    ("gap_strength_continuation", ("gap", "current_return", "relative_return"), (1, 1, 1)),
    ("gap_repair_confirmation", ("gap", "current_return", "rebound_from_low"), (-1, 1, 1)),
    ("opening_range_breakout", ("current_return", "close_location", "path_efficiency"), (1, 1, 1)),
    (
        "opening_volume_breakout",
        ("current_return", "signed_volume_imbalance", "recent_volume_ratio"),
        (1, 1, 1),
    ),
    ("relative_opening_leader", ("relative_return", "current_rank", "path_efficiency"), (1, 1, 1)),
    ("vwap_expansion", ("vwap_distance", "return_acceleration", "close_location"), (1, 1, 1)),
    ("broad_risk_on_open", ("current_return", "sector_breadth", "risk_asset_agreement"), (1, 1, 1)),
    (
        "quiet_opening_momentum",
        ("current_return", "realized_volatility", "path_efficiency"),
        (1, -1, 1),
    ),
    ("prior_weak_open_reversal", ("prior20_return", "gap", "current_return"), (-1, -1, 1)),
    ("gap_flow_agreement", ("gap", "signed_volume_imbalance", "close_location"), (1, 1, 1)),
)
SCHEDULES = ((2, 23), (5, 35), (8, 47), (11, 59), (17, 77))
STATE_MODES = ("unfiltered", "orderly_rebound_cash_filter")


def _configure() -> None:
    strict._configure()
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.FAMILIES = FAMILIES
    campaign.SCHEDULES = SCHEDULES
    campaign.STATE_MODES = STATE_MODES


if __name__ == "__main__":
    _configure()
    campaign.main()
