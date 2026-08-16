"""Afternoon low-volume reclaim multi-factor campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v48_path_range_timing as campaign
import numpy as np

campaign.FACTORS = (
    "volume_acceleration",
    "prior20_return",
    "spy_prior20",
    "vwap_distance",
    "close_location",
    "prior20_rank",
)
campaign.DIRECTION = np.array((-1.0, -1.0, -1.0, 1.0, 1.0, -1.0))
campaign.RELIABILITY = np.array(
    (
        0.077928851075778,
        0.0595980311730927,
        0.019769250712989375,
        0.012768991444127598,
        0.010857863930931688,
        0.008231786362457853,
    )
)
campaign.HORIZONS = ((41, 44, 47, 50),)
campaign.EXITS = (69, 72, 75)
campaign.THRESHOLDS = (0.25, 0.50, 0.75, 1.0)
campaign.CONFIRMATIONS = (1, 2)
campaign.TARGETS = (0.25, 0.30, 0.35)
campaign.LOOKBACKS = (15, 20)
campaign.WEIGHTINGS = ("equal", "reliability")
campaign.CANDIDATE_PREFIX = "lev-v49a-"
campaign.SELECTION_CONTRACT = (
    "afternoon low-volume reclaim factors were selected from a 2022-2025 timing audit; "
    "the bounded family was frozen before diagnostics"
)


if __name__ == "__main__":
    campaign.main()
