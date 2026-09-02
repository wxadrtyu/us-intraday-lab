"""Final bounded lower-quantile extension for causal bar-5 AND gates."""

from __future__ import annotations

import evaluate_full_universe_intraday_v10705_v10804_bar5_logical_ensembles as logical
import numpy as np


FIRST_VERSION = 10805
LAST_VERSION = 10904
PRIOR_COMPARISON_CELLS = 285_583
QUANTILES = (0.0, 0.025, 0.05, 0.075, 0.10)
ALPHAS = (10.0, 30.0, 100.0, 300.0)
PAIR_NAMES = (
    "growth_reclaim_and",
    "absorption_flow_and",
    "growth_flow_and",
    "absorption_growth_and",
    "absorption_reclaim_and",
)
PAIR_SPECS = {name: logical.PAIR_SPECS[name] for name in PAIR_NAMES}
FACTOR_SETS = {name: (name,) for name in PAIR_NAMES}


def _fit_boundary(cube, stream, active, factors, quantile, alpha):
    name = factors[0]
    left_name, right_name, mode = PAIR_SPECS[name]
    left = logical._original_fit(
        cube, stream, active, logical.DEVELOPMENT_FAMILIES[left_name], quantile, alpha
    )
    right = logical._original_fit(
        cube, stream, active, logical.DEVELOPMENT_FAMILIES[right_name], quantile, alpha
    )
    return {
        "logical_ensemble": True,
        "name": name,
        "mode": mode,
        "left": left,
        "right": right,
        "factors": (name,),
        "mean": np.asarray([0.0]),
        "scale": np.asarray([1.0]),
        "coefficients": np.asarray([1.0]),
        "threshold": 0.0,
    }


def _configure() -> None:
    logical._configure()
    campaign = logical.clock.parent.parent.sparse_veto.campaign
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.FACTOR_SETS = FACTOR_SETS
    campaign.QUANTILES = QUANTILES
    campaign.ALPHAS = ALPHAS
    campaign.quality._fit = _fit_boundary
    campaign.MECHANISM = "causal_bar5_and_gate_lower_quantile_boundary"


if __name__ == "__main__":
    _configure()
    logical.clock.parent.parent.sparse_veto.campaign.main()
