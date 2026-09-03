"""Causal volume-clock participation-shock alpha."""

from __future__ import annotations

from dataclasses import dataclass

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import numpy as np

FIRST_VERSION = 13909
LAST_VERSION = 14008
PRIOR_COMPARISON_CELLS = 333_183
ASSETS = np.asarray((3, 4), dtype=int)
SECTORS = np.arange(5, 16, dtype=int)
SCHEDULES = (
    (8, 35), (11, 41), (14, 47), (17, 53), (20, 59),
    (23, 65), (29, 71), (35, 72), (41, 77), (47, 77),
)
WINDOW_BY_SCHEDULE = {
    schedule: (2, 3, 4, 5, 6)[index % 5] for index, schedule in enumerate(SCHEDULES)
}
PARTICIPATION_SETS = {
    "cumulative_surprise": ("cum",),
    "recent_velocity": ("recent",),
    "volume_acceleration": ("accel",),
    "spy_participation_gap": ("rel_spy",),
    "qqq_participation_gap": ("rel_qqq",),
    "sector_participation_gap": ("rel_sector",),
    "price_impact": ("impact",),
    "shock_alignment": ("cum", "recent", "accel"),
    "context_alignment": ("rel_spy", "rel_qqq", "rel_sector"),
    "broad_participation": (
        "cum", "recent", "accel", "rel_spy", "rel_qqq", "rel_sector", "impact"
    ),
}


@dataclass(slots=True)
class VolumeClockModel:
    family: str
    components: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    window_bars: int
    cumulative_baseline: np.ndarray
    recent_baseline: np.ndarray
    prior_baseline: np.ndarray


def _volume_windows(cube, decision, window_bars):
    volume = cube.bar_volume[:, : decision + 1, :]
    split = max(0, decision + 1 - window_bars)
    prior_split = max(0, split - window_bars)
    cumulative = np.nansum(volume, axis=1)
    recent = np.nansum(volume[:, split:, :], axis=1)
    prior = np.nansum(volume[:, prior_split:split, :], axis=1)
    return cumulative, recent, prior


def _baseline(cube, decision, window_bars):
    cumulative, recent, prior = _volume_windows(cube, decision, window_bars)
    train = cube.masks()["train_2022_2023"]
    return tuple(np.nanmedian(item[train], axis=0) for item in (cumulative, recent, prior))


def _safe_log_ratio(value, baseline):
    return np.log((value + 1.0) / (baseline[None, :] + 1.0))


def _participation_matrix(cube, model):
    cumulative, recent, prior = _volume_windows(
        cube, model.decision, model.window_bars
    )
    cum = _safe_log_ratio(cumulative, model.cumulative_baseline)
    rec = _safe_log_ratio(recent, model.recent_baseline)
    old = _safe_log_ratio(prior, model.prior_baseline)
    accel = rec - old
    factors = cube.factors(model.decision)
    current_return = factors["current_return"]
    components = {
        "cum": cum[:, ASSETS],
        "recent": rec[:, ASSETS],
        "accel": accel[:, ASSETS],
        "rel_spy": cum[:, ASSETS] - cum[:, 0, None],
        "rel_qqq": cum[:, ASSETS] - cum[:, 1, None],
        "rel_sector": cum[:, ASSETS] - np.nanmean(cum[:, SECTORS], axis=1)[:, None],
        "impact": current_return[:, ASSETS] / np.sqrt(np.maximum(cumulative[:, ASSETS], 1.0)),
    }
    return np.stack([components[name] for name in model.components], axis=2)


def _fit(cube, family, schedule):
    components = PARTICIPATION_SETS[family]
    decision, exit_bar = schedule
    window_bars = WINDOW_BY_SCHEDULE[schedule]
    baselines = _baseline(cube, decision, window_bars)
    shell = VolumeClockModel(
        family, components, decision, exit_bar, np.empty(0), np.empty(0),
        np.empty(0), window_bars, *baselines
    )
    matrix = _participation_matrix(cube, shell)
    entry = decision + 1
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
    shell.mean, shell.scale, shell.coefficients = mean, scale, coefficients
    return shell


def _scores(cube, model):
    matrix = _participation_matrix(cube, model)
    score = np.einsum(
        "saf,f->sa", (matrix - model.mean) / model.scale, model.coefficients
    )
    return np.where(np.isfinite(matrix).all(axis=2), score, -np.inf)


def _configure() -> None:
    base.FIRST_VERSION = FIRST_VERSION
    base.LAST_VERSION = LAST_VERSION
    base.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    base.ASSETS = ASSETS
    base.FACTOR_SETS = PARTICIPATION_SETS
    base.SCHEDULES = SCHEDULES
    base.TOP_K = (1,)
    base.QUANTILES = (0.0, 0.20, 0.40, 0.60, 0.80)
    base.TARGETS = (0.25, 0.40)
    base.MECHANISM = "causal_volume_clock_participation_shock_alpha"
    base.DEFINITION_EXTRA = lambda model: {
        "window_bars": model.window_bars,
        "window_minutes": model.window_bars * 5,
        "feature_transform": "training_volume_clock_participation_surprise",
        "seasonality_fit": "train_2022_2023_only",
        "training_target": "asset_return_minus_spy_return",
    }
    base._fit = _fit
    base._scores = _scores


if __name__ == "__main__":
    _configure()
    base.main()
