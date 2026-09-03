"""Causal sector-breadth pulse and propagation alpha."""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import numpy as np

FIRST_VERSION = 13809
LAST_VERSION = 13908
PRIOR_COMPARISON_CELLS = 332_183
ASSETS = np.asarray((3, 4), dtype=int)
SECTORS = np.arange(5, 16, dtype=int)
SCHEDULES = (
    (8, 35), (11, 41), (14, 47), (17, 53), (20, 59),
    (23, 65), (29, 71), (35, 72), (41, 77), (47, 77),
)
LAG_BY_SCHEDULE = {
    schedule: (2, 3, 4, 5, 6)[index % 5] for index, schedule in enumerate(SCHEDULES)
}
BREADTH_SETS = {
    "return_breadth": ("current_return",),
    "relative_breadth": ("relative_return",),
    "vwap_breadth": ("vwap_distance",),
    "flow_breadth": ("signed_volume_imbalance",),
    "volume_pulse": ("volume_acceleration",),
    "close_location_breadth": ("close_location",),
    "return_flow_joint": ("current_return", "signed_volume_imbalance"),
    "relative_vwap_joint": ("relative_return", "vwap_distance"),
    "return_vwap_flow": ("current_return", "vwap_distance", "signed_volume_imbalance"),
    "broad_propagation": (
        "current_return", "relative_return", "vwap_distance", "signed_volume_imbalance"
    ),
}
_MATRIX_CACHE: dict[tuple[int, tuple[str, ...], int, int], np.ndarray] = {}


@dataclass(slots=True)
class BreadthPulseModel:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    lag_bars: int


def _breadth_matrix(cube, factors, decision, lag_bars):
    key = (id(cube), tuple(factors), decision, lag_bars)
    if key in _MATRIX_CACHE:
        return _MATRIX_CACHE[key]
    current = cube.factors(decision)
    earlier = cube.factors(decision - lag_bars)
    pieces = []
    for name in factors:
        now_sector = current[name][:, SECTORS]
        prior_sector = earlier[name][:, SECTORS]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=RuntimeWarning)
            now_mean = np.nanmean(now_sector, axis=1)
            prior_mean = np.nanmean(prior_sector, axis=1)
        now_share = np.nanmean(now_sector > 0.0, axis=1)
        prior_share = np.nanmean(prior_sector > 0.0, axis=1)
        mean_pulse = now_mean - prior_mean
        share_pulse = now_share - prior_share
        asset = current[name][:, ASSETS]
        relative = asset - now_mean[:, None]
        pieces.extend(
            (
                relative,
                np.broadcast_to(now_share[:, None], relative.shape),
                relative * mean_pulse[:, None],
                relative * share_pulse[:, None],
            )
        )
    matrix = np.stack(pieces, axis=2)
    _MATRIX_CACHE[key] = matrix
    return matrix


def _fit(cube, family, schedule):
    factors = BREADTH_SETS[family]
    decision, exit_bar = schedule
    lag_bars = LAG_BY_SCHEDULE[schedule]
    entry = decision + 1
    matrix = _breadth_matrix(cube, factors, decision, lag_bars)
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
    return BreadthPulseModel(
        family, factors, decision, exit_bar, mean, scale, coefficients, lag_bars
    )


def _scores(cube, model):
    matrix = _breadth_matrix(cube, model.factors, model.decision, model.lag_bars)
    score = np.einsum(
        "saf,f->sa", (matrix - model.mean) / model.scale, model.coefficients
    )
    return np.where(np.isfinite(matrix).all(axis=2), score, -np.inf)


def _configure() -> None:
    base.FIRST_VERSION = FIRST_VERSION
    base.LAST_VERSION = LAST_VERSION
    base.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    base.ASSETS = ASSETS
    base.FACTOR_SETS = BREADTH_SETS
    base.SCHEDULES = SCHEDULES
    base.TOP_K = (1,)
    base.QUANTILES = (0.0, 0.20, 0.40, 0.60, 0.80)
    base.TARGETS = (0.25, 0.40)
    base.MECHANISM = "causal_sector_breadth_pulse_propagation_alpha"
    base.DEFINITION_EXTRA = lambda model: {
        "lag_bars": model.lag_bars,
        "lag_minutes": model.lag_bars * 5,
        "feature_transform": "sector_breadth_pulse_x_asset_relative_state",
        "sector_count": len(SECTORS),
        "training_target": "asset_return_minus_spy_return",
    }
    base._fit = _fit
    base._scores = _scores


if __name__ == "__main__":
    _configure()
    base.main()
