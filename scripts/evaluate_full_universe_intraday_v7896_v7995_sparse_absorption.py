"""v7896-v7995: sparse pre-route liquidity-absorption sleeve."""

from __future__ import annotations

import evaluate_full_universe_intraday_v6995_v7094_opening_late_ensemble as campaign

FIRST_VERSION = 7896
LAST_VERSION = 7995
PRIOR_COMPARISON_CELLS = 256_766
ABSORPTION_SLOT = (11, 23)
ABSORPTION_FAMILY = "sparse_liquidity_absorption"
ABSORPTION_QUANTILE = 0.80
ABSORPTION_ALPHA = 1000.0
ABSORPTION_FACTORS = (
    "signed_volume_imbalance",
    "volume_acceleration",
    "vwap_distance",
    "close_location",
    "range_ratio",
    "realized_volatility",
    "relative_return",
    "sector_breadth",
)


def _configure():
    campaign.OPENING_SLOT = ABSORPTION_SLOT
    campaign.OPENING_FAMILY = ABSORPTION_FAMILY
    campaign.OPENING_QUANTILE = ABSORPTION_QUANTILE
    campaign.OPENING_ALPHA = ABSORPTION_ALPHA
    campaign.residual.FACTOR_SETS[ABSORPTION_FAMILY] = ABSORPTION_FACTORS
    campaign._configure()
    campaign.campaign.FIRST_VERSION = FIRST_VERSION
    campaign.campaign.LAST_VERSION = LAST_VERSION
    campaign.campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.campaign.EXTRA_COMPONENT_DEFINITION.update(
        {
            "type": "nonoverlapping_sparse_preroute_liquidity_absorption",
            "late_route_entry": 24,
        }
    )


if __name__ == "__main__":
    _configure()
    campaign.campaign.main()
