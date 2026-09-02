"""Independent midday exhaustion-repair return source."""

from __future__ import annotations

import evaluate_full_universe_intraday_v550_v649_state_gated_reversal as campaign
import evaluate_full_universe_intraday_v7695_v7794_midday_cross_sectional as strict

FIRST_VERSION = 11408
LAST_VERSION = 11507
PRIOR_COMPARISON_CELLS = 298_883
FAMILIES = (
    (
        "sector_capitulation_repair",
        ("relative_return", "signed_volume_imbalance", "sector_signed_flow_breadth"),
        (-1, -1, 1),
    ),
    (
        "breadth_snapback_laggard",
        ("current_rank", "rebound_from_low", "sector_breadth_acceleration"),
        (-1, 1, 1),
    ),
    (
        "failed_breakdown_reclaim",
        ("drawdown_from_high", "rebound_from_low", "vwap_distance"),
        (-1, 1, 1),
    ),
    (
        "dispersion_laggard_repair",
        ("relative_return", "sector_flow_dispersion", "sector_return_flow_agreement"),
        (-1, 1, 1),
    ),
    (
        "flow_price_divergence",
        ("current_return", "signed_volume_imbalance", "return_acceleration"),
        (-1, 1, 1),
    ),
    (
        "range_location_repair",
        ("intraday_range_position", "close_location", "rebound_from_low"),
        (-1, 1, 1),
    ),
    (
        "volatility_contraction_reentry",
        ("recent_volatility_ratio", "return_acceleration", "sector_volatility_contraction"),
        (-1, 1, -1),
    ),
    (
        "growth_rotation_repair",
        ("relative_return", "growth_minus_defensive_return", "growth_minus_defensive_flow"),
        (-1, 1, 1),
    ),
    (
        "rank_laggard_sector_turn",
        ("current_rank", "sector_breadth_acceleration", "sector_path_efficiency_breadth"),
        (-1, 1, 1),
    ),
    (
        "balanced_exhaustion_repair",
        (
            "current_return",
            "relative_return",
            "rebound_from_low",
            "return_acceleration",
            "signed_volume_imbalance",
            "sector_breadth_acceleration",
        ),
        (-1, -1, 1, 1, -1, 1),
    ),
)
SCHEDULES = ((23, 47), (29, 59), (35, 65), (41, 72), (47, 77))
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
