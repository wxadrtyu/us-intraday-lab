"""v6795-v6894: causal volatility scaling over the disjoint cash-fill route."""

from __future__ import annotations

import evaluate_full_universe_intraday_v42_multifactor_vol_target as v42
import evaluate_full_universe_intraday_v6395_v6494_cash_fill as cash_fill

FIRST_VERSION = 6795
LAST_VERSION = 6894
PRIOR_COMPARISON_CELLS = 255_655
LOOKBACK = 20
TARGET_VOLATILITY = 0.30
MINIMUM_EXPOSURE = 0.25


def _scale(streams):
    return tuple(
        v42._scaled(
            stream,
            v42._exposure(stream.values, LOOKBACK, TARGET_VOLATILITY, MINIMUM_EXPOSURE),
        )
        for stream in streams
    )


def _configure():
    cash_fill._configure()
    campaign = cash_fill.campaign
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.MECHANISM = "causal_vol_scaled_bar2_cash_fill"
    campaign.STREAM_TRANSFORM = _scale
    campaign.OVERLAY_DEFINITION = {
        "type": "trailing_realized_volatility",
        "lookback_sessions": LOOKBACK,
        "target_annualized_volatility": TARGET_VOLATILITY,
        "minimum_exposure": MINIMUM_EXPOSURE,
        "maximum_exposure": 1.0,
    }


if __name__ == "__main__":
    _configure()
    cash_fill.campaign.main()
