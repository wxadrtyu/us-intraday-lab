"""v8096-v8195: sparse opening-auction absorption sleeve."""

from __future__ import annotations

import evaluate_full_universe_intraday_v6995_v7094_opening_late_ensemble as campaign

FIRST_VERSION = 8096
LAST_VERSION = 8195
PRIOR_COMPARISON_CELLS = 256_966
OPENING_SLOT = (2, 11)
OPENING_FAMILY = "opening_auction_absorption"
OPENING_QUANTILE = 0.80
OPENING_ALPHA = 1000.0
OPENING_FACTORS = (
    "signed_volume_imbalance",
    "volume_acceleration",
    "trend_consistency",
    "vwap_distance",
    "close_location",
    "range_ratio",
    "relative_return",
    "sector_breadth",
)


def _configure():
    campaign.OPENING_SLOT = OPENING_SLOT
    campaign.OPENING_FAMILY = OPENING_FAMILY
    campaign.OPENING_QUANTILE = OPENING_QUANTILE
    campaign.OPENING_ALPHA = OPENING_ALPHA
    campaign.residual.FACTOR_SETS[OPENING_FAMILY] = OPENING_FACTORS
    campaign._configure()
    campaign.campaign.FIRST_VERSION = FIRST_VERSION
    campaign.campaign.LAST_VERSION = LAST_VERSION
    campaign.campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.campaign.EXTRA_COMPONENT_DEFINITION.update(
        {
            "type": "nonoverlapping_sparse_opening_auction_absorption",
            "late_route_entry": 24,
        }
    )


if __name__ == "__main__":
    _configure()
    campaign.campaign.main()
