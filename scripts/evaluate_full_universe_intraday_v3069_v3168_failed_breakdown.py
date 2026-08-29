"""Late-session failed-breakdown and flow-absorption multifactor campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v1463_v1562_intraday_path_multifactor as path

campaign = path.campaign


def configure() -> None:
    campaign.FIRST_VERSION = 3069
    campaign.LAST_VERSION = 3168
    campaign.PRIOR_COMPARISON_CELLS = 112_105
    campaign.prior.v53.Cube = path.IntradayPathCube
    campaign.HISTORICAL_MIN_ANNUALIZED_RETURN = 0.15
    campaign.REQUIRE_CONSUMED_2026Q1_GATE = True
    campaign.FAMILIES = (
        (
            "failed_breakdown_flow_absorption",
            ("drawdown_from_high", "rebound_from_low", "return_acceleration", "signed_volume_imbalance"),
            (-1, 1, 1, 1),
        ),
        (
            "failed_breakdown_relative_reclaim",
            ("drawdown_from_high", "relative_return", "rebound_from_low", "close_location"),
            (-1, -1, 1, 1),
        ),
        (
            "capitulation_range_recovery",
            ("drawdown_from_high", "intraday_range_position", "recent_return", "volume_acceleration"),
            (-1, 1, 1, -1),
        ),
        (
            "quiet_drawdown_reacceleration",
            ("drawdown_from_high", "recent_volatility_ratio", "return_acceleration", "path_efficiency"),
            (-1, -1, 1, 1),
        ),
        (
            "vwap_reclaim_flow_turn",
            ("vwap_distance", "return_acceleration", "signed_volume_imbalance", "close_location"),
            (1, 1, 1, 1),
        ),
        (
            "low_rank_rebound_confirmation",
            ("current_rank", "rebound_from_low", "recent_return", "path_efficiency"),
            (-1, 1, 1, 1),
        ),
        (
            "volatility_compression_reclaim",
            ("recent_volatility_ratio", "rebound_from_low", "return_acceleration", "close_location"),
            (-1, 1, 1, 1),
        ),
        (
            "volume_exhaustion_recovery",
            ("recent_volume_ratio", "drawdown_from_high", "rebound_from_low", "return_acceleration"),
            (-1, -1, 1, 1),
        ),
        (
            "relative_laggard_range_turn",
            ("relative_return", "intraday_range_position", "rebound_from_low", "signed_volume_imbalance"),
            (-1, 1, 1, 1),
        ),
        (
            "breadth_confirmed_path_recovery",
            ("rebound_from_low", "return_acceleration", "risk_asset_agreement", "sector_breadth"),
            (1, 1, 1, 1),
        ),
    )
    campaign.SCHEDULES = ((47, 59), (47, 65), (53, 65), (53, 72), (59, 72))
    campaign.STATE_MODES = ("unfiltered", "orderly_rebound_cash_filter")


if __name__ == "__main__":
    configure()
    campaign.main()
