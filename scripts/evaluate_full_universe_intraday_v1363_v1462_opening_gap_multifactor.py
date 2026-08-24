"""v1363-v1462 preregistered opening-gap multi-factor campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v550_v649_state_gated_reversal as campaign


def main() -> None:
    campaign.FIRST_VERSION = 1363
    campaign.LAST_VERSION = 1462
    campaign.PRIOR_COMPARISON_CELLS = 68_355
    campaign.FAMILIES = (
        (
            "opening_gap_down_vwap_reclaim",
            ("gap", "recent_return", "vwap_distance"),
            (-1, 1, 1),
        ),
        (
            "opening_gap_down_range_recovery",
            ("gap", "relative_return", "close_location"),
            (-1, 1, 1),
        ),
        (
            "opening_gap_follow_confirmation",
            ("gap", "current_return", "path_efficiency"),
            (1, 1, 1),
        ),
        (
            "opening_prior_weak_gap_rebound",
            ("prior20_return", "gap", "recent_return"),
            (-1, -1, 1),
        ),
        (
            "opening_rank_laggard_reclaim",
            ("current_rank", "recent_return", "vwap_distance"),
            (-1, 1, 1),
        ),
        (
            "opening_relative_strength_flow",
            ("current_return", "relative_return", "signed_volume_imbalance"),
            (1, 1, 1),
        ),
        (
            "opening_low_volatility_breakout",
            ("current_return", "path_efficiency", "realized_volatility"),
            (1, 1, -1),
        ),
        (
            "opening_flow_persistence",
            ("recent_return", "signed_volume_imbalance", "volume_acceleration"),
            (1, 1, -1),
        ),
        (
            "opening_residual_reclaim",
            ("leverage_residual", "vwap_distance", "close_location"),
            (-1, 1, 1),
        ),
        (
            "opening_risk_adjusted_reacceleration",
            ("current_return", "recent_return", "realized_volatility"),
            (1, 1, -1),
        ),
    )
    campaign.SCHEDULES = ((5, 20), (8, 23), (11, 29), (14, 35), (17, 41))
    campaign.STATE_MODES = ("unfiltered", "orderly_rebound_cash_filter")
    campaign.main()


if __name__ == "__main__":
    main()
