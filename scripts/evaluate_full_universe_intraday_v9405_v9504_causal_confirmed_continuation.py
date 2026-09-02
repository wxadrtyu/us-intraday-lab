"""v9405-v9504 causal confirmed intraday continuation campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v7695_v7794_midday_cross_sectional as campaign

FIRST_VERSION = 9405
LAST_VERSION = 9504
PRIOR_COMPARISON_CELLS = 270_983

FAMILIES = (
    (
        "relative_strength_flow_confirmation",
        ("relative_return", "signed_volume_imbalance", "sector_return_flow_agreement"),
        (1, 1, 1),
    ),
    (
        "efficient_breakout",
        ("relative_return", "path_efficiency", "close_location"),
        (1, 1, 1),
    ),
    (
        "vwap_hold_broadening",
        ("vwap_distance", "sector_breadth_acceleration", "sector_path_efficiency_breadth"),
        (1, 1, 1),
    ),
    (
        "quiet_relative_breakout",
        ("relative_return", "recent_volatility_ratio", "range_ratio"),
        (1, -1, -1),
    ),
    (
        "sector_flow_leader",
        ("current_rank", "sector_signed_flow_breadth", "sector_leadership_spread"),
        (1, 1, 1),
    ),
    (
        "growth_risk_leadership",
        ("relative_return", "growth_minus_defensive_return", "risk_asset_agreement"),
        (1, 1, 1),
    ),
    (
        "residual_momentum",
        ("leverage_residual", "return_acceleration", "signed_volume_imbalance"),
        (1, 1, 1),
    ),
    (
        "range_high_persistence",
        ("intraday_range_position", "close_location", "trend_consistency"),
        (1, 1, 1),
    ),
    (
        "broadening_rank_persistence",
        ("current_rank", "sector_breadth", "sector_breadth_acceleration"),
        (1, 1, 1),
    ),
    (
        "flow_acceleration_leader",
        ("relative_return", "volume_acceleration", "sector_flow_dispersion"),
        (1, 1, 1),
    ),
)

SCHEDULES = ((5, 17), (11, 23), (17, 29), (35, 47), (53, 65))
STATE_MODES = ("unfiltered", "orderly_rebound_cash_filter")


def _configure() -> None:
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.FAMILIES = FAMILIES
    campaign.SCHEDULES = SCHEDULES
    campaign.STATE_MODES = STATE_MODES
    campaign.HISTORICAL_MIN_ANNUALIZED_RETURN = 0.15
    campaign.REQUIRE_CONSUMED_2026Q1_GATE = True
    campaign._configure()


if __name__ == "__main__":
    _configure()
    campaign.campaign.main()
