"""v450-v549 preregistered causal-state and independent-rule campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v349_v448_preregistered_campaign as campaign

campaign.FIRST_VERSION = 450
campaign.LAST_VERSION = 549
campaign.PRIOR_COMPARISON_CELLS = 37_744

campaign.STATE_CONCEPTS = (
    ("liquid_growth_risk_on", {"spy_current": 1.0, "qqq_current": 1.0, "sector_breadth": 1.0}),
    (
        "small_cap_reflation",
        {"iwm_current": 1.0, "cyclical_minus_defensive": 1.0, "sector_breadth": 1.0},
    ),
    (
        "orderly_technology_leadership",
        {"tech_minus_market": 1.0, "risk_asset_agreement": 1.0, "sector_dispersion": -1.0},
    ),
    (
        "orderly_cyclical_leadership",
        {"cyclical_minus_defensive": 1.0, "risk_asset_agreement": 1.0, "sector_dispersion": -1.0},
    ),
    ("calm_large_cap_breadth", {"qqq_current": 1.0, "sector_breadth": 1.0, "spy_volatility": -1.0}),
    ("calm_small_cap_breadth", {"iwm_current": 1.0, "sector_breadth": 1.0, "spy_volatility": -1.0}),
    (
        "broad_growth_without_stress",
        {"qqq_minus_iwm": 1.0, "sector_breadth": 1.0, "spy_volatility": -1.0},
    ),
    (
        "broad_value_without_stress",
        {"qqq_minus_iwm": -1.0, "sector_breadth": 1.0, "spy_volatility": -1.0},
    ),
    (
        "market_tech_cyclical_alignment",
        {"spy_current": 1.0, "tech_minus_market": 1.0, "cyclical_minus_defensive": 1.0},
    ),
    (
        "index_agreement_low_dispersion",
        {"qqq_current": 1.0, "iwm_current": 1.0, "sector_dispersion": -1.0},
    ),
    (
        "index_agreement_low_volatility",
        {"qqq_current": 1.0, "iwm_current": 1.0, "spy_volatility": -1.0},
    ),
    (
        "breadth_agreement_low_volatility",
        {"sector_breadth": 1.0, "risk_asset_agreement": 1.0, "spy_volatility": -1.0},
    ),
    (
        "technology_breadth_agreement",
        {"tech_minus_market": 1.0, "sector_breadth": 1.0, "risk_asset_agreement": 1.0},
    ),
    (
        "cyclical_breadth_agreement",
        {"cyclical_minus_defensive": 1.0, "sector_breadth": 1.0, "risk_asset_agreement": 1.0},
    ),
    (
        "large_cap_defensive_rotation",
        {"qqq_current": 1.0, "cyclical_minus_defensive": -1.0, "spy_volatility": -1.0},
    ),
    (
        "small_cap_cyclical_rotation",
        {"iwm_current": 1.0, "cyclical_minus_defensive": 1.0, "spy_volatility": -1.0},
    ),
    (
        "broad_market_without_tech_concentration",
        {"spy_current": 1.0, "sector_breadth": 1.0, "tech_minus_market": -1.0},
    ),
    (
        "broad_market_without_small_cap_lag",
        {"spy_current": 1.0, "iwm_current": 1.0, "qqq_minus_iwm": -1.0},
    ),
    (
        "growth_leadership_with_agreement",
        {"qqq_minus_iwm": 1.0, "tech_minus_market": 1.0, "risk_asset_agreement": 1.0},
    ),
    (
        "reflation_with_agreement",
        {"qqq_minus_iwm": -1.0, "cyclical_minus_defensive": 1.0, "risk_asset_agreement": 1.0},
    ),
    (
        "four_way_orderly_risk_on",
        {
            "spy_current": 1.0,
            "sector_breadth": 1.0,
            "risk_asset_agreement": 1.0,
            "spy_volatility": -1.0,
        },
    ),
    (
        "four_way_orderly_growth",
        {
            "qqq_current": 1.0,
            "tech_minus_market": 1.0,
            "sector_dispersion": -1.0,
            "spy_volatility": -1.0,
        },
    ),
    (
        "four_way_orderly_reflation",
        {
            "iwm_current": 1.0,
            "cyclical_minus_defensive": 1.0,
            "sector_dispersion": -1.0,
            "spy_volatility": -1.0,
        },
    ),
    (
        "four_way_broad_alignment",
        {"spy_current": 1.0, "qqq_current": 1.0, "iwm_current": 1.0, "sector_breadth": 1.0},
    ),
    (
        "four_way_dispersion_avoidance",
        {
            "sector_breadth": 1.0,
            "risk_asset_agreement": 1.0,
            "sector_dispersion": -1.0,
            "spy_volatility": -1.0,
        },
    ),
)
campaign.STATE_CLOCKS = ("bar17", "prior_close")

campaign.RULE_FAMILIES = (
    ("ranked_vwap_persistence", ("current_rank", "vwap_distance", "path_efficiency"), (1, 1, 1)),
    (
        "residual_flow_persistence",
        ("leverage_residual", "signed_volume_imbalance", "volume_acceleration"),
        (1, 1, -1),
    ),
    (
        "low_vol_relative_strength",
        ("relative_return", "realized_volatility", "close_location"),
        (1, -1, 1),
    ),
    (
        "prior_strength_reacceleration",
        ("prior20_return", "recent_return", "volume_acceleration"),
        (1, 1, -1),
    ),
    ("prior_rank_reacceleration", ("prior20_rank", "current_rank", "path_efficiency"), (-1, 1, 1)),
    ("gap_residual_confirmation", ("gap", "leverage_residual", "relative_return"), (1, 1, 1)),
    (
        "vwap_compression_release",
        ("vwap_distance", "realized_volatility", "current_return"),
        (1, -1, 1),
    ),
    (
        "efficient_flow_reversal",
        ("recent_return", "path_efficiency", "signed_volume_imbalance"),
        (-1, 1, 1),
    ),
    (
        "cross_section_close_confirmation",
        ("current_rank", "relative_return", "close_location"),
        (1, 1, 1),
    ),
    (
        "residual_rank_flow_consensus",
        ("leverage_residual", "current_rank", "signed_volume_imbalance", "close_location"),
        (1, 1, 1, 1),
    ),
)
campaign.RULE_SCHEDULES = ((5, 20), (14, 32), (32, 53), (38, 68), (50, 76))


if __name__ == "__main__":
    campaign.main()
