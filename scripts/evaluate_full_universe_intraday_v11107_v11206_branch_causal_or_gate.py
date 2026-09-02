"""Lower-quantile OR gates over the parity-proven branch-causal route."""

from __future__ import annotations

import evaluate_full_universe_intraday_v10705_v10804_bar5_logical_ensembles as logical
import evaluate_full_universe_intraday_v11006_v11105_branch_causal as branch
import numpy as np

FIRST_VERSION = 11107
LAST_VERSION = 11206
PRIOR_COMPARISON_CELLS = 285_883
QUANTILES = (0.0, 0.025, 0.05, 0.075, 0.10)
ALPHAS = (10.0, 30.0, 100.0, 300.0)
PAIR_NAMES = (
    "growth_reclaim_or",
    "absorption_flow_or",
    "growth_flow_or",
    "absorption_growth_or",
    "absorption_reclaim_or",
)
PAIR_SPECS = {name: logical.PAIR_SPECS[name] for name in PAIR_NAMES}
FACTOR_SETS = {name: (name,) for name in PAIR_NAMES}


def _fit_or(cube, stream, active, factors, quantile, alpha):
    name = factors[0]
    left_name, right_name, mode = PAIR_SPECS[name]
    left = logical._original_fit(
        cube,
        stream,
        active,
        logical.DEVELOPMENT_FAMILIES[left_name],
        quantile,
        alpha,
    )
    right = logical._original_fit(
        cube,
        stream,
        active,
        logical.DEVELOPMENT_FAMILIES[right_name],
        quantile,
        alpha,
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
    branch._configure()
    campaign = branch.boundary.logical.clock.parent.parent.sparse_veto.campaign
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.FACTOR_SETS = FACTOR_SETS
    campaign.QUANTILES = QUANTILES
    campaign.ALPHAS = ALPHAS
    campaign.quality._fit = _fit_or
    campaign.MECHANISM = "branch_causal_lower_quantile_or_gate"


if __name__ == "__main__":
    _configure()
    branch.boundary.logical.clock.parent.parent.sparse_veto.campaign.main()
