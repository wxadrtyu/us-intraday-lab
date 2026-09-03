"""Causal intraday factor-state transition alpha."""

from __future__ import annotations

from dataclasses import dataclass

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import numpy as np

FIRST_VERSION = 13509
LAST_VERSION = 13608
PRIOR_COMPARISON_CELLS = 329_183
ASSETS = np.asarray((3, 4), dtype=int)
SCHEDULES = base.residual.SCHEDULES
LAG_BY_SCHEDULE = {
    schedule: (2, 3, 4, 5, 6)[index % 5] for index, schedule in enumerate(SCHEDULES)
}


@dataclass(slots=True)
class StateDeltaModel:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    lag_bars: int


def _delta_matrix(cube, factors, decision, lag_bars):
    current = cube.factors(decision)
    previous = cube.factors(max(0, decision - lag_bars))
    return np.stack(
        [current[name][:, ASSETS] - previous[name][:, ASSETS] for name in factors],
        axis=2,
    )


def _fit(cube, family, schedule):
    factors = base.residual.FACTOR_SETS[family]
    decision, exit_bar = schedule
    lag_bars = LAG_BY_SCHEDULE[schedule]
    entry = decision + 1
    matrix = _delta_matrix(cube, factors, decision, lag_bars)
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
    return StateDeltaModel(
        family,
        factors,
        int(decision),
        int(exit_bar),
        mean,
        scale,
        coefficients,
        lag_bars,
    )


def _scores(cube, model):
    matrix = _delta_matrix(
        cube, model.factors, model.decision, model.lag_bars
    )
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
    base.SCHEDULES = SCHEDULES
    base.TOP_K = (1,)
    base.QUANTILES = (0.0, 0.20, 0.40, 0.60, 0.80)
    base.TARGETS = (0.25, 0.40)
    base.MECHANISM = "causal_intraday_factor_state_delta_alpha"
    base.DEFINITION_EXTRA = lambda model: {
        "lag_bars": model.lag_bars,
        "lag_minutes": model.lag_bars * 5,
        "feature_transform": "decision_state_minus_lagged_state",
        "training_target": "asset_return_minus_spy_return",
    }
    base._fit = _fit
    base._scores = _scores


if __name__ == "__main__":
    _configure()
    base.main()
