"""Preregistered v653-v752 cross-sectional contraction/leadership campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v550_v649_state_gated_reversal as campaign


def main() -> None:
    campaign.FIRST_VERSION = 653
    campaign.LAST_VERSION = 752
    campaign.PRIOR_COMPARISON_CELLS = 53_194
    campaign.STATE_FACTORS = {
        "spy_current": 1.0,
        "sector_breadth": 1.0,
        "risk_asset_agreement": 1.0,
        "sector_dispersion": -1.0,
    }
    campaign.FAMILIES = (
        (
            "compressed_relative_breakout",
            ("relative_return", "range_ratio", "path_efficiency"),
            (1, -1, 1),
        ),
        (
            "low_volatility_vwap_reclaim",
            ("realized_volatility", "vwap_distance", "recent_return"),
            (-1, 1, 1),
        ),
        (
            "breadth_confirmed_rank_leader",
            ("current_rank", "sector_breadth", "path_efficiency"),
            (1, 1, 1),
        ),
        (
            "contracted_range_reacceleration",
            ("session_range", "recent_return", "volume_acceleration"),
            (-1, 1, 1),
        ),
        (
            "persistent_leader_pullback_recovery",
            ("prior20_rank", "recent_return", "close_location"),
            (1, 1, 1),
        ),
        (
            "orderly_relative_strength",
            ("relative_return", "path_efficiency", "signed_volume_imbalance"),
            (1, 1, 1),
        ),
        (
            "failed_breakout_reclaim",
            ("range_ratio", "vwap_distance", "close_location"),
            (-1, 1, 1),
        ),
        (
            "cross_section_acceleration",
            ("current_rank", "recent_return", "volume_acceleration"),
            (1, 1, 1),
        ),
        (
            "calm_flow_leadership",
            ("realized_volatility", "signed_volume_imbalance", "current_rank"),
            (-1, 1, 1),
        ),
        (
            "prior_strength_vwap_confirmation",
            ("prior20_return", "vwap_distance", "path_efficiency"),
            (1, 1, 1),
        ),
    )
    campaign.SCHEDULES = ((23, 47), (29, 53), (35, 59), (41, 65), (47, 72))
    campaign.STATE_MODES = ("unfiltered", "orderly_rebound_cash_filter")
    campaign.main()


if __name__ == "__main__":
    main()
