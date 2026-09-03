"""Dual-model standardized score ensembles for leveraged intraday selection."""

from __future__ import annotations

from dataclasses import dataclass

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import numpy as np

FIRST_VERSION = 12109
LAST_VERSION = 12208
PRIOR_COMPARISON_CELLS = 314_583
PAIR_SPECS = {
    "trend_flow__reclaim_flow": ("trend_flow_state", "reclaim_flow"),
    "trend_structure__contraction": ("trend_structure", "contraction_breakout"),
    "cross_persistence__gap_repair": ("cross_persistence", "gap_repair"),
    "relative_leadership__volatility_flow": ("relative_leadership", "volatility_flow"),
    "balanced_path__failed_breakdown": ("balanced_path", "failed_breakdown"),
    "trend_flow__contraction": ("trend_flow_state", "contraction_breakout"),
    "trend_structure__reclaim_flow": ("trend_structure", "reclaim_flow"),
    "cross_persistence__relative_leadership": ("cross_persistence", "relative_leadership"),
    "gap_repair__failed_breakdown": ("gap_repair", "failed_breakdown"),
    "balanced_path__volatility_flow": ("balanced_path", "volatility_flow"),
}


@dataclass(slots=True)
class EnsembleModel:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    members: tuple[object, object]


def _member_score(cube, model):
    matrix = base.residual._matrix(cube, model.factors, model.decision)
    score = np.einsum(
        "saf,f->sa", (matrix - model.mean) / model.scale, model.coefficients
    )
    return np.where(np.isfinite(matrix).all(axis=2), score, np.nan)


def _fit(cube, family, schedule):
    members = tuple(
        base.residual._fit(cube, name, schedule, 0.0, base.ALPHA)
        for name in PAIR_SPECS[family]
    )
    scores = np.stack([_member_score(cube, item) for item in members], axis=2)
    train = cube.masks()["train_2022_2023"][:, None, None]
    selected = scores[np.broadcast_to(train, scores.shape) & np.isfinite(scores)]
    # Per-member normalization makes the ensemble invariant to ridge score scale.
    means = np.asarray(
        [np.nanmean(scores[cube.masks()["train_2022_2023"], :, i]) for i in range(2)]
    )
    scales = np.asarray(
        [np.nanstd(scores[cube.masks()["train_2022_2023"], :, i]) for i in range(2)]
    )
    del selected
    scales[scales < 1e-12] = 1.0
    return EnsembleModel(
        family,
        tuple(PAIR_SPECS[family]),
        int(schedule[0]),
        int(schedule[1]),
        means,
        scales,
        np.asarray([0.5, 0.5]),
        members,
    )


def _scores(cube, model):
    members = np.stack([_member_score(cube, item) for item in model.members], axis=2)
    standardized = (members - model.mean) / model.scale
    score = np.nanmean(standardized, axis=2)
    return np.where(np.isfinite(members).all(axis=2), score, -np.inf)


def _configure() -> None:
    base.FIRST_VERSION = FIRST_VERSION
    base.LAST_VERSION = LAST_VERSION
    base.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    base.ASSETS = np.asarray((3, 4), dtype=int)
    base.FACTOR_SETS = PAIR_SPECS
    base.TOP_K = (1,)
    base.QUANTILES = (0.0, 0.20, 0.40, 0.60, 0.80)
    base.TARGETS = (0.25, 0.40)
    base.MECHANISM = "dual_model_standardized_score_ensemble"
    base._fit = _fit
    base._scores = _scores


if __name__ == "__main__":
    _configure()
    base.main()
