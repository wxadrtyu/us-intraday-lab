"""v1664-v1763 preregistered state and independent path/flow campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v349_v448_preregistered_campaign as campaign

campaign.FIRST_VERSION = 1664
campaign.LAST_VERSION = 1763
campaign.PRIOR_COMPARISON_CELLS = 94_355

campaign.STATE_CONCEPTS = (
    (
        "breadth_recovery_after_stress",
        {"sector_breadth": 1.0, "spy_volatility": 1.0, "spy_current": 1.0},
    ),
    (
        "small_cap_recovery_after_stress",
        {"iwm_current": 1.0, "spy_volatility": 1.0, "qqq_minus_iwm": -1.0},
    ),
    (
        "technology_recovery_after_stress",
        {"qqq_current": 1.0, "spy_volatility": 1.0, "tech_minus_market": 1.0},
    ),
    (
        "cyclical_recovery_after_stress",
        {"spy_current": 1.0, "spy_volatility": 1.0, "cyclical_minus_defensive": 1.0},
    ),
    (
        "dispersion_reversal_breadth",
        {"sector_dispersion": 1.0, "sector_breadth": 1.0, "spy_current": 1.0},
    ),
    (
        "dispersion_reversal_agreement",
        {"sector_dispersion": 1.0, "risk_asset_agreement": 1.0, "spy_current": 1.0},
    ),
    (
        "growth_rotation_with_breadth",
        {"qqq_minus_iwm": 1.0, "sector_breadth": 1.0, "spy_current": 1.0},
    ),
    (
        "value_rotation_with_breadth",
        {"qqq_minus_iwm": -1.0, "sector_breadth": 1.0, "spy_current": 1.0},
    ),
    (
        "technology_rotation_with_cyclicals",
        {"tech_minus_market": 1.0, "cyclical_minus_defensive": 1.0, "spy_current": 1.0},
    ),
    (
        "defensive_rotation_with_agreement",
        {"cyclical_minus_defensive": -1.0, "risk_asset_agreement": 1.0, "spy_current": 1.0},
    ),
    (
        "volatile_but_broad_risk_on",
        {"spy_volatility": 1.0, "sector_breadth": 1.0, "risk_asset_agreement": 1.0},
    ),
    (
        "volatile_large_cap_leadership",
        {"spy_volatility": 1.0, "qqq_current": 1.0, "iwm_current": -1.0},
    ),
    (
        "volatile_small_cap_leadership",
        {"spy_volatility": 1.0, "iwm_current": 1.0, "qqq_current": -1.0},
    ),
    (
        "high_dispersion_tech_leadership",
        {"sector_dispersion": 1.0, "tech_minus_market": 1.0, "qqq_current": 1.0},
    ),
    (
        "high_dispersion_cyclical_leadership",
        {"sector_dispersion": 1.0, "cyclical_minus_defensive": 1.0, "iwm_current": 1.0},
    ),
    ("broad_market_lag_recovery", {"spy_current": 1.0, "qqq_current": -1.0, "iwm_current": -1.0}),
    ("growth_lag_recovery", {"qqq_current": 1.0, "qqq_minus_iwm": 1.0, "tech_minus_market": -1.0}),
    (
        "small_cap_lag_recovery",
        {"iwm_current": 1.0, "qqq_minus_iwm": -1.0, "cyclical_minus_defensive": -1.0},
    ),
    (
        "breadth_without_index_agreement",
        {"sector_breadth": 1.0, "risk_asset_agreement": -1.0, "spy_current": 1.0},
    ),
    (
        "agreement_without_breadth",
        {"risk_asset_agreement": 1.0, "sector_breadth": -1.0, "spy_current": 1.0},
    ),
    (
        "four_way_stress_recovery",
        {
            "spy_current": 1.0,
            "spy_volatility": 1.0,
            "sector_breadth": 1.0,
            "sector_dispersion": 1.0,
        },
    ),
    (
        "four_way_growth_recovery",
        {"qqq_current": 1.0, "qqq_minus_iwm": 1.0, "tech_minus_market": 1.0, "spy_volatility": 1.0},
    ),
    (
        "four_way_reflation_recovery",
        {
            "iwm_current": 1.0,
            "qqq_minus_iwm": -1.0,
            "cyclical_minus_defensive": 1.0,
            "spy_volatility": 1.0,
        },
    ),
    (
        "four_way_rotation_agreement",
        {
            "risk_asset_agreement": 1.0,
            "sector_dispersion": 1.0,
            "tech_minus_market": 1.0,
            "cyclical_minus_defensive": 1.0,
        },
    ),
    (
        "four_way_breadth_repair",
        {"spy_current": 1.0, "qqq_current": 1.0, "iwm_current": 1.0, "sector_dispersion": 1.0},
    ),
)
campaign.STATE_CLOCKS = ("bar17", "prior_close")

campaign.RULE_FAMILIES = (
    (
        "path_efficient_laggard_turn",
        ("prior20_rank", "recent_return", "path_efficiency", "close_location"),
        (-1, 1, 1, 1),
    ),
    (
        "flow_absorption_reversal",
        ("recent_return", "signed_volume_imbalance", "volume_acceleration", "close_location"),
        (-1, 1, -1, 1),
    ),
    (
        "residual_pullback_reclaim",
        ("leverage_residual", "recent_return", "vwap_distance"),
        (-1, 1, 1),
    ),
    (
        "quiet_rank_reacceleration",
        ("current_rank", "realized_volatility", "volume_acceleration"),
        (1, -1, -1),
    ),
    ("gap_absorption_reclaim", ("gap", "signed_volume_imbalance", "vwap_distance"), (-1, 1, 1)),
    (
        "prior_weakness_flow_turn",
        ("prior20_return", "signed_volume_imbalance", "close_location"),
        (-1, 1, 1),
    ),
    (
        "compressed_residual_breakout",
        ("leverage_residual", "realized_volatility", "path_efficiency"),
        (1, -1, 1),
    ),
    (
        "ranked_volume_reacceleration",
        ("current_rank", "volume_acceleration", "current_return"),
        (1, -1, 1),
    ),
    ("relative_vwap_path_turn", ("relative_return", "vwap_distance", "path_efficiency"), (1, 1, 1)),
    (
        "five_factor_recovery_consensus",
        (
            "prior20_return",
            "recent_return",
            "vwap_distance",
            "signed_volume_imbalance",
            "close_location",
        ),
        (-1, 1, 1, 1, 1),
    ),
)
campaign.RULE_SCHEDULES = ((7, 27), (18, 39), (27, 58), (44, 70), (56, 77))


if __name__ == "__main__":
    campaign.main()
