"""v957-v1056 preregistered full-portfolio cash-routing campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v753_v852_dual_component_routing as campaign


def main() -> None:
    campaign.FIRST_VERSION = 957
    campaign.LAST_VERSION = 1056
    campaign.PRIOR_COMPARISON_CELLS = 66_755
    campaign.ROUTE_ANCHOR = True
    campaign.TOTAL_WEIGHTS = (0.05, 0.10, 0.15, 0.20, 0.25)
    campaign.V247_SHARES = (0.0, 0.25, 0.50, 0.75, 1.0)
    campaign.STATE_QUANTILES = (0.10, 0.20, 0.30, 0.40)
    campaign.ROUTING_MODES = (
        (
            "prior_close_trend_breadth_cash",
            "prior_close",
            {
                "spy_current": 1.0,
                "qqq_current": 1.0,
                "sector_breadth": 1.0,
                "spy_volatility": -1.0,
            },
        ),
        (
            "prior_close_low_dispersion_cash",
            "prior_close",
            {
                "spy_current": 1.0,
                "risk_asset_agreement": 1.0,
                "sector_dispersion": -1.0,
                "spy_volatility": -1.0,
            },
        ),
        (
            "prior_close_defensive_resilience_cash",
            "prior_close",
            {
                "spy_current": 1.0,
                "sector_breadth": 1.0,
                "cyclical_minus_defensive": -1.0,
                "spy_volatility": -1.0,
            },
        ),
        (
            "prior_close_cross_asset_confirmation_cash",
            "prior_close",
            {
                "spy_current": 1.0,
                "qqq_current": 1.0,
                "iwm_current": 1.0,
                "risk_asset_agreement": 1.0,
            },
        ),
    )
    campaign.main()


if __name__ == "__main__":
    main()
