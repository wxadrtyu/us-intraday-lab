"""v7696-v7795: pre-route intraday reversal sleeve plus late state route."""

from __future__ import annotations

import evaluate_full_universe_intraday_v6995_v7094_opening_late_ensemble as campaign

FIRST_VERSION = 7696
LAST_VERSION = 7795
PRIOR_COMPARISON_CELLS = 256_566
PREROUTE_SLOT = (11, 23)
PREROUTE_FAMILY = "intraday_reversal_quality"
PREROUTE_QUANTILE = 0.50
PREROUTE_ALPHA = 100.0
PREROUTE_FACTORS = (
    "current_return",
    "recent_return",
    "relative_return",
    "vwap_distance",
    "close_location",
    "path_efficiency",
    "signed_volume_imbalance",
    "spy_prior20",
)


def _configure():
    campaign.OPENING_SLOT = PREROUTE_SLOT
    campaign.OPENING_FAMILY = PREROUTE_FAMILY
    campaign.OPENING_QUANTILE = PREROUTE_QUANTILE
    campaign.OPENING_ALPHA = PREROUTE_ALPHA
    campaign.residual.FACTOR_SETS[PREROUTE_FAMILY] = PREROUTE_FACTORS
    campaign._configure()
    campaign.campaign.FIRST_VERSION = FIRST_VERSION
    campaign.campaign.LAST_VERSION = LAST_VERSION
    campaign.campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.campaign.EXTRA_COMPONENT_DEFINITION.update(
        {
            "type": "nonoverlapping_preroute_intraday_reversal",
            "late_route_entry": 24,
        }
    )


if __name__ == "__main__":
    _configure()
    campaign.campaign.main()
