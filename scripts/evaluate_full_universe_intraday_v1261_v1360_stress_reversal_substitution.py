"""v1261-v1360 preregistered stress-state reversal substitution campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v753_v852_dual_component_routing as campaign


def main() -> None:
    campaign.FIRST_VERSION = 1261
    campaign.LAST_VERSION = 1360
    campaign.PRIOR_COMPARISON_CELLS = 67_955
    campaign.ROUTE_ANCHOR = False
    campaign.REALLOCATE_TO_ANCHOR_WHEN_BLOCKED = True
    campaign.RANK_MODE = "stress_floor"
    campaign.FIRST_COMPONENT_NAME = "reversal"
    campaign.SECOND_COMPONENT_NAME = "continuation"
    campaign.COMPONENT_IDS = {
        "reversal": "lev-v580-a8e415fa00879183",
        "continuation": "lev-v60-b528b229cefeace2",
    }
    campaign.TOTAL_WEIGHTS = (0.02, 0.04, 0.06, 0.08, 0.10)
    campaign.V247_SHARES = (0.0, 0.25, 0.50, 0.75, 1.0)
    campaign.STATE_QUANTILES = (0.20, 0.35, 0.50, 0.65)
    campaign.ROUTING_MODES = (
        (
            "prior_close_disorderly_reversal_substitution",
            "prior_close",
            {
                "sector_breadth": -1.0,
                "risk_asset_agreement": -1.0,
                "sector_dispersion": 1.0,
                "spy_volatility": 1.0,
            },
        ),
        (
            "prior_close_defensive_rotation_reversal_substitution",
            "prior_close",
            {
                "spy_current": -1.0,
                "iwm_current": -1.0,
                "cyclical_minus_defensive": -1.0,
                "spy_volatility": 1.0,
            },
        ),
        (
            "bar17_broad_selloff_reversal_substitution",
            "bar17",
            {
                "spy_current": -1.0,
                "qqq_current": -1.0,
                "sector_breadth": -1.0,
                "risk_asset_agreement": -1.0,
            },
        ),
        (
            "bar17_cross_section_dislocation_reversal_substitution",
            "bar17",
            {
                "sector_breadth": -1.0,
                "sector_dispersion": 1.0,
                "tech_minus_market": -1.0,
                "spy_volatility": 1.0,
            },
        ),
    )
    campaign.main()


if __name__ == "__main__":
    main()
