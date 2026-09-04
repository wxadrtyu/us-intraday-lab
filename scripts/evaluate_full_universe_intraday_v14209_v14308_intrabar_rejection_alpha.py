"""Causal completed-candle body and wick rejection alpha."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import numpy as np
import search_full_universe_intraday_v21_vwap_structure as v21
from evaluate_full_universe_intraday_v1463_v1562_intraday_path_multifactor import (
    IntradayPathCube,
)

FIRST_VERSION = 14209
LAST_VERSION = 14308
PRIOR_COMPARISON_CELLS = 336_183
ASSETS = np.asarray((3, 4), dtype=int)
SCHEDULES = (
    (9, 35),
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
REPRESENTATIONS = {
    "last_completed_candle": ("last", 1),
    "short_equal_rejection": ("equal", 3),
    "medium_equal_rejection": ("equal", 5),
    "long_equal_rejection": ("equal", 8),
    "recency_weighted_rejection": ("recency", 5),
    "range_weighted_rejection": ("range", 5),
    "body_weighted_rejection": ("body", 5),
    "lower_wick_absorption_events": ("lower_event", 5),
    "upper_wick_failure_events": ("upper_event", 5),
    "early_late_rejection_contrast": ("phase", 8),
}
FACTORS = (
    "weighted_body",
    "weighted_rejection",
    "weighted_lower_wick",
    "weighted_upper_wick",
    "positive_rejection_share",
    "last_rejection",
    "rejection_phase_change",
)
_MATRIX_CACHE: dict[tuple, np.ndarray] = {}


class WickCube(IntradayPathCube):
    def __init__(self, root: Path, source: str, boundary_tolerance: int) -> None:
        super().__init__(root, source, boundary_tolerance)
        frame = v21._load_microstructure(root, source)
        self.highs = v21.v11._cube(frame, self.sessions, "high")
        self.lows = v21.v11._cube(frame, self.sessions, "low")


@dataclass(slots=True)
class WickModel:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    mode: str
    window_bars: int


def _weighted_mean(values: np.ndarray, weights: np.ndarray) -> np.ndarray:
    denominator = np.sum(weights, axis=1)
    return np.divide(
        np.sum(values * weights, axis=1),
        denominator,
        out=np.full(values.shape[0], np.nan),
        where=denominator > 0,
    )


def _wick_features(cube, model: WickModel, asset: int) -> np.ndarray:
    start = model.decision - model.window_bars + 1
    opens = cube.opens[:, start : model.decision + 1, asset]
    highs = cube.highs[:, start : model.decision + 1, asset]
    lows = cube.lows[:, start : model.decision + 1, asset]
    closes = cube.closes[:, start : model.decision + 1, asset]
    spread = highs - lows
    valid = (
        np.isfinite(opens).all(axis=1)
        & np.isfinite(highs).all(axis=1)
        & np.isfinite(lows).all(axis=1)
        & np.isfinite(closes).all(axis=1)
        & (spread > 0).all(axis=1)
    )
    body = np.divide(closes - opens, spread, out=np.zeros_like(spread), where=spread > 0)
    lower = np.divide(
        np.minimum(opens, closes) - lows,
        spread,
        out=np.zeros_like(spread),
        where=spread > 0,
    )
    upper = np.divide(
        highs - np.maximum(opens, closes),
        spread,
        out=np.zeros_like(spread),
        where=spread > 0,
    )
    rejection = lower - upper
    weights = np.ones_like(spread)
    if model.mode == "last":
        weights[:, :-1] = 0.0
    elif model.mode == "recency":
        weights *= np.linspace(1.0, 2.0, model.window_bars)
    elif model.mode == "range":
        weights *= spread / np.maximum(np.nanmean(spread, axis=1)[:, None], 1e-12)
    elif model.mode == "body":
        weights *= np.abs(body) + 0.10
    elif model.mode == "lower_event":
        weights *= lower > upper
    elif model.mode == "upper_event":
        weights *= upper > lower
    elif model.mode in {"equal", "phase"}:
        pass
    else:
        raise ValueError(f"UNKNOWN_WICK_MODE:{model.mode}")
    split = max(1, model.window_bars // 2)
    phase = (
        np.zeros(rejection.shape[0])
        if model.window_bars == 1
        else np.mean(rejection[:, split:], axis=1)
        - np.mean(rejection[:, :split], axis=1)
    )
    result = np.stack(
        (
            _weighted_mean(body, weights),
            _weighted_mean(rejection, weights),
            _weighted_mean(lower, weights),
            _weighted_mean(upper, weights),
            np.mean(rejection > 0, axis=1),
            rejection[:, -1],
            phase,
        ),
        axis=1,
    )
    result[~valid] = np.nan
    return result


def _wick_matrix(cube, model: WickModel) -> np.ndarray:
    key = (id(cube), model.family, model.decision, model.exit_bar, model.mode, model.window_bars)
    if key not in _MATRIX_CACHE:
        _MATRIX_CACHE[key] = np.stack(
            [_wick_features(cube, model, int(asset)) for asset in ASSETS], axis=1
        )
    return _MATRIX_CACHE[key]


def _fit(cube, family, schedule):
    mode, window = REPRESENTATIONS[family]
    decision, exit_bar = schedule
    shell = WickModel(
        family,
        FACTORS,
        decision,
        exit_bar,
        np.empty(0),
        np.empty(0),
        np.empty(0),
        mode,
        window,
    )
    matrix = _wick_matrix(cube, shell)
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
    matrix = _wick_matrix(cube, model)
    score = np.einsum(
        "saf,f->sa", (matrix - model.mean) / model.scale, model.coefficients
    )
    return np.where(np.isfinite(matrix).all(axis=2), score, -np.inf)


def _configure() -> None:
    base.FIRST_VERSION = FIRST_VERSION
    base.LAST_VERSION = LAST_VERSION
    base.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    base.IntradayPathCube = WickCube
    base.ASSETS = ASSETS
    base.FACTOR_SETS = REPRESENTATIONS
    base.SCHEDULES = SCHEDULES
    base.TOP_K = (1,)
    base.QUANTILES = (0.0, 0.20, 0.40, 0.60, 0.80)
    base.TARGETS = (0.25, 0.40)
    base.MECHANISM = "causal_completed_candle_rejection_alpha"
    base.DEFINITION_EXTRA = lambda model: {
        "wick_mode": model.mode,
        "window_bars": model.window_bars,
        "feature_transform": "completed_candle_body_and_wick_rejection",
        "training_target": "asset_return_minus_spy_return",
    }
    base._fit = _fit
    base._scores = _scores


if __name__ == "__main__":
    _configure()
    base.main()
