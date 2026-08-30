"""v7596-v7695: short opening gap-repair source before the late route."""

from __future__ import annotations

import evaluate_full_universe_intraday_v6995_v7094_opening_late_ensemble as campaign

FIRST_VERSION = 7596
LAST_VERSION = 7695
PRIOR_COMPARISON_CELLS = 256_466
OPENING_SLOT = (2, 11)
OPENING_FAMILY = "short_gap_reversal"
OPENING_QUANTILE = 0.50
OPENING_ALPHA = 100.0
OPENING_FACTORS = (
    "gap",
    "current_return",
    "relative_return",
    "vwap_distance",
    "close_location",
    "spy_prior20",
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
            "type": "nonoverlapping_short_opening_gap_repair",
            "late_route_entry": 24,
        }
    )


if __name__ == "__main__":
    _configure()
    campaign.campaign.main()
