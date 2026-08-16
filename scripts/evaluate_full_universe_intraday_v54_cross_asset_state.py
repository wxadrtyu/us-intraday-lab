"""Cross-asset state confirmation added to the leveraged-ETF factor signal."""

from __future__ import annotations

import analyze_full_universe_intraday_v53_cross_asset_factors as v53
import evaluate_full_universe_intraday_v44_multihorizon_confirmation as v44
import evaluate_full_universe_intraday_v48_path_range_timing as v48
import numpy as np

if __name__ == "__main__":
    v48.FACTORS = (
        *v44.FACTORS,
        "tech_minus_market",
        "leverage_residual",
        "qqq_current",
    )
    v48.DIRECTION = np.array((1.0, -1.0, -1.0, -1.0, 1.0, -1.0, 1.0))
    v48.RELIABILITY = np.array(
        (
            0.0051,
            0.0300,
            0.0299,
            0.0494,
            0.0295,
            0.0101,
            0.0040,
        )
    )
    v48.HORIZONS = ((20, 23, 26), (23, 26))
    v48.EXITS = (69, 72)
    v48.THRESHOLDS = (0.25, 0.50, 0.75, 1.0)
    v48.CONFIRMATIONS = (1, 2)
    v48.CANDIDATE_PREFIX = "lev-v54x-"
    v48.CUBE_CLASS = v53.Cube
    v48.SELECTION_CONTRACT = (
        "cross-asset factors had stable signs in 2022-2023, 2024, and 2025 at "
        "the selected horizons; the 384-cell family was frozen before historical "
        "and consumed-2026 diagnostics"
    )
    v48.main()
