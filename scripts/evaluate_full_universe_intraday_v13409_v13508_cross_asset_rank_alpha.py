"""Cross-asset nonlinear rank transforms for leveraged intraday alpha."""

from __future__ import annotations

from dataclasses import dataclass

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import numpy as np

FIRST_VERSION = 13409
LAST_VERSION = 13508
PRIOR_COMPARISON_CELLS = 328_183
ASSETS = np.asarray((3, 4), dtype=int)
RANK_UNIVERSE = np.arange(3, 16, dtype=int)


@dataclass(slots=True)
class RankModel:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray


def _rank_matrix(cube, factors, decision):
    available = cube.factors(decision)
    pieces = []
    for factor in factors:
        values = available[factor][:, RANK_UNIVERSE]
        finite = np.isfinite(values)
        ordered = np.argsort(np.where(finite, values, np.inf), axis=1)
        ranks = np.argsort(ordered, axis=1).astype(float) / (len(RANK_UNIVERSE) - 1)
        ranks[~finite] = np.nan
        pieces.append(ranks[:, : len(ASSETS)])
    return np.stack(pieces, axis=2)


def _fit(cube, family, schedule):
    factors = base.residual.FACTOR_SETS[family]
    decision, exit_bar = schedule
    entry = decision + 1
    matrix = _rank_matrix(cube, factors, decision)
    asset_return = cube.opens[:, exit_bar, ASSETS] / cube.opens[:, entry, ASSETS] - 1.0
    spy_return = cube.opens[:, exit_bar, 0] / cube.opens[:, entry, 0] - 1.0
    target = asset_return - spy_return[:, None]
    quality = (
        (cube.first[:, entry, ASSETS] <= entry * 5)
        & (cube.first[:, exit_bar, ASSETS] <= exit_bar * 5)
        & np.isfinite(matrix).all(axis=2)
        & np.isfinite(target)
    )
    train = cube.masks()["train_2022_2023"][:, None] & quality
    values, labels = matrix[train], target[train]
    mean, scale = values.mean(axis=0), values.std(axis=0)
    scale[scale < 1e-8] = 1.0
    standardized = (values - mean) / scale
    coefficients = np.linalg.solve(
        standardized.T @ standardized + base.ALPHA * np.eye(len(factors)),
        standardized.T @ labels,
    )
    return RankModel(
        family,
        factors,
        int(decision),
        int(exit_bar),
        mean,
        scale,
        coefficients,
    )


def _scores(cube, model):
    matrix = _rank_matrix(cube, model.factors, model.decision)
    score = np.einsum(
        "saf,f->sa", (matrix - model.mean) / model.scale, model.coefficients
    )
    return np.where(np.isfinite(matrix).all(axis=2), score, -np.inf)


def _configure() -> None:
    base.FIRST_VERSION = FIRST_VERSION
    base.LAST_VERSION = LAST_VERSION
    base.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    base.ASSETS = ASSETS
    base.FACTOR_SETS = base.residual.FACTOR_SETS
    base.SCHEDULES = base.residual.SCHEDULES
    base.TOP_K = (1,)
    base.QUANTILES = (0.0, 0.20, 0.40, 0.60, 0.80)
    base.TARGETS = (0.25, 0.40)
    base.MECHANISM = "cross_asset_nonlinear_percentile_rank_alpha"
    base.DEFINITION_EXTRA = lambda _model: {
        "transform": "session_cross_asset_percentile_rank",
        "rank_universe_asset_indexes": RANK_UNIVERSE.tolist(),
        "training_target": "asset_return_minus_spy_return",
    }
    base._fit = _fit
    base._scores = _scores


if __name__ == "__main__":
    _configure()
    base.main()
