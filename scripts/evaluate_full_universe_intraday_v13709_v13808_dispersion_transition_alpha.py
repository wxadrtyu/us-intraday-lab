"""Causal cross-sectional dispersion-transition alpha."""

from __future__ import annotations

from dataclasses import dataclass

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import numpy as np

FIRST_VERSION = 13709
LAST_VERSION = 13808
PRIOR_COMPARISON_CELLS = 331_183
ASSETS = np.asarray((3, 4), dtype=int)
PANEL = np.arange(3, 16, dtype=int)
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
LAG_BY_SCHEDULE = {
    schedule: (2, 3, 4, 5, 6)[index % 5] for index, schedule in enumerate(SCHEDULES)
}


@dataclass(slots=True)
class DispersionTransitionModel:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    lag_bars: int


def _panel_rank(values: np.ndarray) -> np.ndarray:
    finite = np.isfinite(values)
    filled = np.where(finite, values, np.inf)
    order = np.argsort(np.argsort(filled, axis=1), axis=1).astype(float)
    rank = order / max(1, values.shape[1] - 1) - 0.5
    return np.where(finite, rank, np.nan)


def _dispersion_matrix(cube, factors, decision, lag_bars):
    current = cube.factors(decision)
    earlier = cube.factors(decision - lag_bars)
    pieces = []
    for name in factors:
        now = current[name][:, PANEL]
        prior = earlier[name][:, PANEL]
        median = np.nanmedian(now, axis=1)
        prior_median = np.nanmedian(prior, axis=1)
        mad = np.nanmedian(np.abs(now - median[:, None]), axis=1)
        prior_mad = np.nanmedian(np.abs(prior - prior_median[:, None]), axis=1)
        scale = np.maximum(mad, 1e-8)
        dispersion_change = np.log((mad + 1e-8) / (prior_mad + 1e-8))
        q25, q75 = np.nanpercentile(now, (25, 75), axis=1)
        tail_asymmetry = ((q75 - median) - (median - q25)) / scale
        normalized = (now[:, :2] - median[:, None]) / scale[:, None]
        rank = _panel_rank(now)[:, :2]
        pieces.extend(
            (
                normalized,
                rank,
                normalized * dispersion_change[:, None],
                rank * tail_asymmetry[:, None],
            )
        )
    return np.stack(pieces, axis=2)


def _fit(cube, family, schedule):
    factors = base.residual.FACTOR_SETS[family]
    decision, exit_bar = schedule
    lag_bars = LAG_BY_SCHEDULE[schedule]
    entry = decision + 1
    matrix = _dispersion_matrix(cube, factors, decision, lag_bars)
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
        standardized.T @ standardized + base.ALPHA * np.eye(matrix.shape[2]),
        standardized.T @ labels,
    )
    return DispersionTransitionModel(
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
    matrix = _dispersion_matrix(
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
    base.MECHANISM = "causal_cross_sectional_dispersion_transition_alpha"
    base.DEFINITION_EXTRA = lambda model: {
        "lag_bars": model.lag_bars,
        "lag_minutes": model.lag_bars * 5,
        "feature_transform": "panel_rank_deviation_x_dispersion_transition",
        "panel_size": len(PANEL),
        "training_target": "asset_return_minus_spy_return",
    }
    base._fit = _fit
    base._scores = _scores


if __name__ == "__main__":
    _configure()
    base.main()
