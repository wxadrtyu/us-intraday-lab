"""v6895-v6994 prior-close state-interaction fill campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v6695_v6794_state_gated_wide_fill as campaign

FIRST_VERSION = 6895
LAST_VERSION = 6994
PRIOR_COMPARISON_CELLS = 255_755

STATE_FAMILIES = {
    "defensive_leadership": {
        "spy_current": 1,
        "cyclical_minus_defensive": -1,
        "sector_breadth": 1,
        "spy_volatility": -1,
    },
    "quiet_growth_repair": {
        "qqq_current": -1,
        "tech_minus_market": 1,
        "sector_dispersion": -1,
        "spy_volatility": -1,
    },
    "broad_oversold_stability": {
        "spy_current": -1,
        "sector_breadth": 1,
        "sector_dispersion": -1,
        "risk_asset_agreement": 1,
    },
    "smallcap_growth_divergence": {
        "iwm_current": 1,
        "qqq_minus_iwm": 1,
        "tech_minus_market": 1,
        "sector_breadth": 1,
    },
    "cyclical_low_vol": {
        "cyclical_minus_defensive": 1,
        "sector_dispersion": -1,
        "spy_current": 1,
        "spy_volatility": -1,
    },
    "volatile_breadth_repair": {
        "spy_volatility": 1,
        "spy_current": -1,
        "sector_breadth": 1,
        "risk_asset_agreement": 1,
    },
    "tech_without_concentration": {
        "qqq_current": 1,
        "tech_minus_market": 1,
        "sector_dispersion": -1,
        "risk_asset_agreement": 1,
    },
    "smallcap_confirmation_low_vol": {
        "iwm_current": 1,
        "qqq_minus_iwm": -1,
        "sector_dispersion": -1,
        "spy_volatility": -1,
    },
    "risk_agreement_repair": {
        "spy_current": -1,
        "qqq_current": -1,
        "iwm_current": -1,
        "risk_asset_agreement": 1,
        "sector_breadth": 1,
    },
    "balanced_defensive_growth": {
        "spy_current": 1,
        "qqq_current": 1,
        "iwm_current": 1,
        "cyclical_minus_defensive": -1,
        "sector_breadth": 1,
        "sector_dispersion": -1,
        "spy_volatility": -1,
    },
}


def _configure() -> None:
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.state.STATE_FAMILIES = STATE_FAMILIES


if __name__ == "__main__":
    _configure()
    campaign.main()
