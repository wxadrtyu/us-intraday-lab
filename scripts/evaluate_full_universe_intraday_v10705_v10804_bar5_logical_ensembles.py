"""Causal bar-5 logical ensembles of development-ranked quality gates."""

from __future__ import annotations

import evaluate_full_universe_intraday_v10305_v10604_causal_gate_clock as clock
import evaluate_full_universe_intraday_v10605_v10704_bar5_development_composites as composites
import numpy as np


FIRST_VERSION = 10705
LAST_VERSION = 10804
PRIOR_COMPARISON_CELLS = 285_483

ORIGINAL = clock.parent.parent.sparse_veto.campaign.FACTOR_SETS
DEVELOPMENT_FAMILIES = {
    "absorption": ORIGINAL["relative_absorption"],
    "growth": ORIGINAL["growth_risk"],
    "reclaim": ORIGINAL["unstable_reclaim"],
    "flow_repair": composites.FACTOR_SETS["flow_repair_quality"],
}
PAIR_SPECS = {
    "absorption_growth_and": ("absorption", "growth", "and"),
    "absorption_growth_or": ("absorption", "growth", "or"),
    "absorption_reclaim_and": ("absorption", "reclaim", "and"),
    "absorption_reclaim_or": ("absorption", "reclaim", "or"),
    "absorption_flow_and": ("absorption", "flow_repair", "and"),
    "absorption_flow_or": ("absorption", "flow_repair", "or"),
    "growth_reclaim_and": ("growth", "reclaim", "and"),
    "growth_reclaim_or": ("growth", "reclaim", "or"),
    "growth_flow_and": ("growth", "flow_repair", "and"),
    "growth_flow_or": ("growth", "flow_repair", "or"),
}
FACTOR_SETS = {name: (name,) for name in PAIR_SPECS}
_original_fit = clock.parent.parent.sparse_veto.campaign.quality._fit
_original_score = clock.parent.parent.sparse_veto.campaign.quality._score


def _fit_logical(cube, stream, active, factors, quantile, alpha):
    name = factors[0]
    left_name, right_name, mode = PAIR_SPECS[name]
    left = _original_fit(
        cube, stream, active, DEVELOPMENT_FAMILIES[left_name], quantile, alpha
    )
    right = _original_fit(
        cube, stream, active, DEVELOPMENT_FAMILIES[right_name], quantile, alpha
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


def _score_logical(cube, model):
    if not model.get("logical_ensemble"):
        return _original_score(cube, model)
    left_score = _original_score(cube, model["left"])
    right_score = _original_score(cube, model["right"])
    left = np.isfinite(left_score) & (left_score >= model["left"]["threshold"])
    right = np.isfinite(right_score) & (right_score >= model["right"]["threshold"])
    allowed = (left & right) if model["mode"] == "and" else (left | right)
    return np.where(allowed, 1.0, -1.0)


def _configure() -> None:
    clock._configure()
    campaign = clock.parent.parent.sparse_veto.campaign
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.FACTOR_SETS = FACTOR_SETS
    campaign.quality._fit = _fit_logical
    campaign.quality._score = _score_logical
    campaign.MECHANISM = "causal_bar5_logical_gate_ensemble"


if __name__ == "__main__":
    _configure()
    clock.parent.parent.sparse_veto.campaign.main()
