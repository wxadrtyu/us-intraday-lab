"""v1563-v1662 preregistered path-component routing campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v753_v852_dual_component_routing as campaign
import evaluate_full_universe_intraday_v1463_v1562_intraday_path_multifactor as path


def main() -> None:
    campaign.FIRST_VERSION = 1563
    campaign.LAST_VERSION = 1662
    campaign.PRIOR_COMPARISON_CELLS = 93_955
    campaign.ROUTE_ANCHOR = False
    campaign.REALLOCATE_TO_ANCHOR_WHEN_BLOCKED = True
    campaign.RANK_MODE = "stress_floor"
    campaign.FIRST_COMPONENT_NAME = "path_turn"
    campaign.SECOND_COMPONENT_NAME = "continuation"
    campaign.COMPONENT_IDS = {
        "path_turn": "lev-v1500-7374c951787a0721",
        "continuation": "lev-v60-b528b229cefeace2",
    }
    campaign.prior.v53.Cube = path.IntradayPathCube
    campaign.TOTAL_WEIGHTS = (0.02, 0.04, 0.06, 0.08, 0.10)
    campaign.V247_SHARES = (0.0, 0.25, 0.50, 0.75, 1.0)
    campaign.STATE_QUANTILES = (0.20, 0.35, 0.50, 0.65)
    campaign.ROUTING_MODES = (
        (
            "prior_close_disorderly_path_substitution",
            "prior_close",
            {
                "sector_breadth": -1.0,
                "risk_asset_agreement": -1.0,
                "sector_dispersion": 1.0,
                "spy_volatility": 1.0,
            },
        ),
        (
            "prior_close_defensive_path_substitution",
            "prior_close",
            {
                "spy_current": -1.0,
                "iwm_current": -1.0,
                "cyclical_minus_defensive": -1.0,
                "spy_volatility": 1.0,
            },
        ),
        (
            "bar17_broad_selloff_path_substitution",
            "bar17",
            {
                "spy_current": -1.0,
                "qqq_current": -1.0,
                "sector_breadth": -1.0,
                "risk_asset_agreement": -1.0,
            },
        ),
        (
            "bar17_cross_section_dislocation_path_substitution",
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
