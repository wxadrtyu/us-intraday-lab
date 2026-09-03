"""Causal intraday factor-state acceleration alpha."""

from __future__ import annotations

from dataclasses import dataclass

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import numpy as np

FIRST_VERSION = 13609
LAST_VERSION = 13708
PRIOR_COMPARISON_CELLS = 330_183
ASSETS = np.asarray((3, 4), dtype=int)
SCHEDULES = (
    (8, 35),
    (11, 41),
    (14, 47),
    (17, 53),
    (20, 59),
    (23, 65),
    (29, 71),
    (35, 72),
    (41, 77),
    (47, 77),
)
STEP_BY_SCHEDULE = {
    schedule: (1, 2, 3, 4, 2, 3, 4, 1, 2, 3)[index]
    for index, schedule in enumerate(SCHEDULES)
}


@dataclass(slots=True)
class StateAccelerationModel:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    step_bars: int


def _acceleration_matrix(cube, factors, decision, step_bars):
    current = cube.factors(decision)
    middle = cube.factors(decision - step_bars)
    earlier = cube.factors(decision - 2 * step_bars)
    return np.stack(
        [
            current[name][:, ASSETS]
            - 2.0 * middle[name][:, ASSETS]
            + earlier[name][:, ASSETS]
            for name in factors
        ],
        axis=2,
    )


def _fit(cube, family, schedule):
    factors = base.residual.FACTOR_SETS[family]
    decision, exit_bar = schedule
    step_bars = STEP_BY_SCHEDULE[schedule]
    entry = decision + 1
    matrix = _acceleration_matrix(cube, factors, decision, step_bars)
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
    return StateAccelerationModel(
        family,
        factors,
        int(decision),
        int(exit_bar),
        mean,
        scale,
        coefficients,
        step_bars,
    )


def _scores(cube, model):
    matrix = _acceleration_matrix(
        cube, model.factors, model.decision, model.step_bars
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
    base.MECHANISM = "causal_intraday_factor_state_acceleration_alpha"
    base.DEFINITION_EXTRA = lambda model: {
        "step_bars": model.step_bars,
        "step_minutes": model.step_bars * 5,
        "total_lookback_minutes": model.step_bars * 10,
        "feature_transform": "current_minus_twice_middle_plus_earlier_state",
        "training_target": "asset_return_minus_spy_return",
    }
    base._fit = _fit
    base._scores = _scores


if __name__ == "__main__":
    _configure()
    base.main()
