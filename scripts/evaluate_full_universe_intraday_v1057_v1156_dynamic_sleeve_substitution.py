"""v1057-v1156 preregistered dynamic sleeve-substitution campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v753_v852_dual_component_routing as campaign


def main() -> None:
    campaign.FIRST_VERSION = 1057
    campaign.LAST_VERSION = 1156
    campaign.PRIOR_COMPARISON_CELLS = 67_155
    campaign.ROUTE_ANCHOR = False
    campaign.REALLOCATE_TO_ANCHOR_WHEN_BLOCKED = True
    campaign.TOTAL_WEIGHTS = (0.02, 0.04, 0.06, 0.08, 0.10)
    campaign.V247_SHARES = (0.0, 0.25, 0.50, 0.75, 1.0)
    campaign.STATE_QUANTILES = (0.10, 0.20, 0.30, 0.40)
    campaign.ROUTING_MODES = (
        (
            "prior_close_orderly_substitution",
            "prior_close",
            {
                "spy_current": 1.0,
                "sector_breadth": 1.0,
                "risk_asset_agreement": 1.0,
                "spy_volatility": -1.0,
            },
        ),
        (
            "prior_close_low_dispersion_substitution",
            "prior_close",
            {
                "spy_current": 1.0,
                "risk_asset_agreement": 1.0,
                "sector_dispersion": -1.0,
                "spy_volatility": -1.0,
            },
        ),
        (
            "prior_close_defensive_substitution",
            "prior_close",
            {
                "spy_current": 1.0,
                "sector_breadth": 1.0,
                "cyclical_minus_defensive": -1.0,
                "spy_volatility": -1.0,
            },
        ),
        (
            "prior_close_growth_substitution",
            "prior_close",
            {
                "qqq_current": 1.0,
                "tech_minus_market": 1.0,
                "sector_breadth": 1.0,
                "sector_dispersion": -1.0,
            },
        ),
    )
    campaign.main()


if __name__ == "__main__":
    main()
