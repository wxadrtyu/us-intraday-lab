"""v9305-v9404 causal intraday recovery campaign.

The batch tests whether a long-only laggard can recover after contemporaneous
liquidity absorption, stabilization, or sector broadening.  Every signal uses
only factors available at the declared decision bar and enters at the next
five-minute open.
"""

from __future__ import annotations

import evaluate_full_universe_intraday_v7695_v7794_midday_cross_sectional as campaign

FIRST_VERSION = 9305
LAST_VERSION = 9404
PRIOR_COMPARISON_CELLS = 258_183

FAMILIES = (
    (
        "relative_laggard_absorption",
        ("relative_return", "signed_volume_imbalance", "close_location"),
        (-1, 1, 1),
    ),
    (
        "intraday_dip_stabilization",
        ("current_return", "recent_return", "close_location"),
        (-1, 1, 1),
    ),
    (
        "flow_divergence_recovery",
        ("recent_return", "signed_volume_imbalance", "volume_acceleration"),
        (-1, 1, -1),
    ),
    (
        "sector_laggard_broadening",
        ("relative_return", "sector_breadth_acceleration", "sector_return_flow_agreement"),
        (-1, 1, 1),
    ),
    (
        "quiet_laggard_reclaim",
        ("relative_return", "recent_volatility_ratio", "path_efficiency"),
        (-1, -1, 1),
    ),
    (
        "range_low_recovery",
        ("intraday_range_position", "rebound_from_low", "close_location"),
        (-1, 1, 1),
    ),
    (
        "residual_laggard_flow",
        ("leverage_residual", "signed_volume_imbalance", "sector_signed_flow_breadth"),
        (-1, 1, 1),
    ),
    (
        "risk_confirmed_laggard",
        ("relative_return", "risk_asset_agreement", "sector_breadth"),
        (-1, 1, 1),
    ),
    (
        "dispersion_reversal",
        ("current_rank", "sector_dispersion", "close_location"),
        (-1, 1, 1),
    ),
    (
        "vwap_recovery_with_flow",
        ("vwap_distance", "signed_volume_imbalance", "sector_path_efficiency_breadth"),
        (-1, 1, 1),
    ),
)

# Each decision is followed by next-bar execution and a same-session exit.
# The separated windows reduce dependence on any one clock-time anomaly.
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
