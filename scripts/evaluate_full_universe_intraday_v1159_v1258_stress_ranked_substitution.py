"""v1159-v1258 preregistered stress-ranked dynamic substitution campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v753_v852_dual_component_routing as campaign


def main() -> None:
    campaign.FIRST_VERSION = 1159
    campaign.LAST_VERSION = 1258
    campaign.PRIOR_COMPARISON_CELLS = 67_555
    campaign.ROUTE_ANCHOR = False
    campaign.REALLOCATE_TO_ANCHOR_WHEN_BLOCKED = True
    campaign.RANK_MODE = "stress_floor"
    campaign.TOTAL_WEIGHTS = (0.08, 0.10, 0.12, 0.14, 0.16)
    campaign.V247_SHARES = (0.0, 0.10, 0.25, 0.50, 0.75)
    campaign.STATE_QUANTILES = (0.15, 0.25, 0.35, 0.45)
    campaign.ROUTING_MODES = (
        (
            "bar17_growth_leadership_substitution",
            "bar17",
            {
                "qqq_current": 1.0,
                "tech_minus_market": 1.0,
                "sector_breadth": 1.0,
                "risk_asset_agreement": 1.0,
            },
        ),
        (
            "bar17_low_dispersion_breakout_substitution",
            "bar17",
            {
                "spy_current": 1.0,
                "qqq_current": 1.0,
                "sector_dispersion": -1.0,
                "spy_volatility": -1.0,
            },
        ),
        (
            "bar17_risk_asset_confirmation_substitution",
            "bar17",
            {
                "spy_current": 1.0,
                "iwm_current": 1.0,
                "sector_breadth": 1.0,
                "risk_asset_agreement": 1.0,
            },
        ),
        (
            "prior_close_volatility_contraction_substitution",
            "prior_close",
            {
                "sector_breadth": 1.0,
                "risk_asset_agreement": 1.0,
                "sector_dispersion": -1.0,
                "spy_volatility": -1.0,
            },
        ),
    )
    campaign.main()


if __name__ == "__main__":
    main()
