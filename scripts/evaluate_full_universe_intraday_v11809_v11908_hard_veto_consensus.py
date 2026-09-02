"""Three- and four-way causal quality consensus over admitted v11800."""

from __future__ import annotations

import evaluate_full_universe_intraday_v10705_v10804_bar5_logical_ensembles as logical
import evaluate_full_universe_intraday_v11708_v11807_branch_causal_hard_veto as hard
import numpy as np

FIRST_VERSION = 11809
LAST_VERSION = 11908
PRIOR_COMPARISON_CELLS = 311_983
QUANTILES = (0.0, 0.025, 0.05, 0.075, 0.10)
ALPHAS = (10.0, 30.0, 100.0, 300.0)
CONSENSUS_SPECS = {
    "without_absorption": ("growth", "reclaim", "flow_repair"),
    "without_growth": ("absorption", "reclaim", "flow_repair"),
    "without_reclaim": ("absorption", "growth", "flow_repair"),
    "without_flow": ("absorption", "growth", "reclaim"),
    "all_four": ("absorption", "growth", "reclaim", "flow_repair"),
}
FACTOR_SETS = {name: (name,) for name in CONSENSUS_SPECS}


def _fit_consensus(cube, stream, active, factors, quantile, alpha):
    name = factors[0]
    members = [
        logical._original_fit(
            cube,
            stream,
            active,
            logical.DEVELOPMENT_FAMILIES[family],
            quantile,
            alpha,
        )
        for family in CONSENSUS_SPECS[name]
    ]
    return {
        "consensus_ensemble": True,
        "name": name,
        "members": members,
        "factors": (name,),
        "mean": np.asarray([0.0]),
        "scale": np.asarray([1.0]),
        "coefficients": np.asarray([1.0]),
        "threshold": 0.0,
    }


def _score_consensus(cube, model):
    if not model.get("consensus_ensemble"):
        return logical._original_score(cube, model)
    passed = np.ones(len(cube.sessions), dtype=bool)
    for member in model["members"]:
        score = logical._original_score(cube, member)
        passed &= np.isfinite(score) & (score >= member["threshold"])
    return np.where(passed, 1.0, -1.0)


def _configure() -> None:
    hard._configure()
    campaign = hard.branch.boundary.logical.clock.parent.parent.sparse_veto.campaign
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.FACTOR_SETS = FACTOR_SETS
    campaign.QUANTILES = QUANTILES
    campaign.ALPHAS = ALPHAS
    campaign.quality._fit = _fit_consensus
    campaign.quality._score = _score_consensus
    campaign.MECHANISM = "branch_causal_hard_cash_three_four_way_quality_consensus"


if __name__ == "__main__":
    _configure()
    hard.branch.boundary.logical.clock.parent.parent.sparse_veto.campaign.main()
