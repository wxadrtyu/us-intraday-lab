"""v855-v954 preregistered cross-asset state routing campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v753_v852_dual_component_routing as campaign


def main() -> None:
    campaign.FIRST_VERSION = 855
    campaign.LAST_VERSION = 954
    campaign.PRIOR_COMPARISON_CELLS = 66_355
    campaign.ROUTING_MODES = (
        (
            "prior_close_defensive_resilience",
            "prior_close",
            {
                "spy_current": 1.0,
                "sector_breadth": 1.0,
                "cyclical_minus_defensive": -1.0,
                "spy_volatility": -1.0,
            },
        ),
        (
            "bar17_growth_breadth",
            "bar17",
            {
                "qqq_current": 1.0,
                "tech_minus_market": 1.0,
                "sector_breadth": 1.0,
                "risk_asset_agreement": 1.0,
            },
        ),
        (
            "prior_close_low_dispersion_alignment",
            "prior_close",
            {
                "spy_current": 1.0,
                "risk_asset_agreement": 1.0,
                "sector_dispersion": -1.0,
                "spy_volatility": -1.0,
            },
        ),
        (
            "bar17_reflation_confirmation",
            "bar17",
            {
                "iwm_current": 1.0,
                "cyclical_minus_defensive": 1.0,
                "sector_breadth": 1.0,
                "qqq_minus_iwm": -1.0,
            },
        ),
    )
    campaign.main()


if __name__ == "__main__":
    main()
