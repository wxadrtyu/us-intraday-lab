"""Pairwise TQQQ-versus-SOXL relative-value prediction."""

from __future__ import annotations

from dataclasses import dataclass

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import numpy as np

FIRST_VERSION = 12309
LAST_VERSION = 12408
PRIOR_COMPARISON_CELLS = 316_183


@dataclass(slots=True)
class PairwiseModel:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray


def _difference_matrix(cube, factors, decision):
    available = cube.factors(decision)
    return np.stack(
        [available[name][:, 3] - available[name][:, 4] for name in factors], axis=1
    )


def _fit(cube, family, schedule):
    factors = base.residual.FACTOR_SETS[family]
    decision, exit_bar = schedule
    entry = decision + 1
    matrix = _difference_matrix(cube, factors, decision)
    tqqq = cube.opens[:, exit_bar, 3] / cube.opens[:, entry, 3] - 1.0
    soxl = cube.opens[:, exit_bar, 4] / cube.opens[:, entry, 4] - 1.0
    target = tqqq - soxl
    quality = (
        (cube.first[:, entry, 3:5] <= entry * 5).all(axis=1)
        & (cube.first[:, exit_bar, 3:5] <= exit_bar * 5).all(axis=1)
        & np.isfinite(target)
        & np.isfinite(matrix).all(axis=1)
    )
    train = cube.masks()["train_2022_2023"] & quality
    values, labels = matrix[train], target[train]
    mean, scale = values.mean(axis=0), values.std(axis=0)
    scale[scale < 1e-8] = 1.0
    standardized = (values - mean) / scale
    coefficients = np.linalg.solve(
        standardized.T @ standardized + base.ALPHA * np.eye(len(factors)),
        standardized.T @ labels,
    )
    return PairwiseModel(
        family, factors, int(decision), int(exit_bar), mean, scale, coefficients
    )


def _scores(cube, model):
    matrix = _difference_matrix(cube, model.factors, model.decision)
    prediction = ((matrix - model.mean) / model.scale) @ model.coefficients
    finite = np.isfinite(matrix).all(axis=1) & np.isfinite(prediction)
    return np.where(finite[:, None], np.stack((prediction, -prediction), axis=1), -np.inf)


def _configure() -> None:
    base.FIRST_VERSION = FIRST_VERSION
    base.LAST_VERSION = LAST_VERSION
    base.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    base.ASSETS = np.asarray((3, 4), dtype=int)
    base.FACTOR_SETS = base.residual.FACTOR_SETS
    base.SCHEDULES = base.residual.SCHEDULES
    base.TOP_K = (1,)
    base.QUANTILES = (0.0, 0.20, 0.40, 0.60, 0.80)
    base.TARGETS = (0.25, 0.40)
    base.MECHANISM = "pairwise_tqqq_soxl_relative_value"
    base.DEFINITION_EXTRA = lambda _model: {
        "target": "future_tqqq_minus_soxl_return",
        "features": "tqqq_minus_soxl_factor_differences",
    }
    base._fit = _fit
    base._scores = _scores


if __name__ == "__main__":
    _configure()
    base.main()
