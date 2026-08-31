"""v8997-v9096 soft-exposure sparse-gap loss-veto campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v8396_v8495_sparse_gap_loss_veto as sparse_veto
import numpy as np

FIRST_VERSION = 8997
LAST_VERSION = 9096
PRIOR_COMPARISON_CELLS = 257_877
QUANTILES = (0.10, 0.15, 0.20, 0.25, 0.30)
ALPHAS = (30.0, 100.0)
LOW_EXPOSURE = 0.25


def _soft_veto(stream, allowed):
    exposure = np.where(allowed, 1.0, LOW_EXPOSURE)
    active = stream.active
    return sparse_veto.campaign.v34.v12.ReturnStream(
        stream.values * exposure,
        stream.benchmark * exposure,
        active,
        stream.component_trades,
    )


def _configure() -> None:
    sparse_veto._configure()
    campaign = sparse_veto.campaign
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.QUANTILES = QUANTILES
    campaign.ALPHAS = ALPHAS
    campaign.STREAM_TRANSFORM = _soft_veto
    campaign.MECHANISM = "sparse_gap_soft_25pct_loss_veto"


if __name__ == "__main__":
    _configure()
    sparse_veto.campaign.main()
