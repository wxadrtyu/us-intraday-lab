"""Causal cross-asset correlation-break and lead-lag alpha."""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import numpy as np

FIRST_VERSION = 14009
LAST_VERSION = 14108
PRIOR_COMPARISON_CELLS = 334_183
ASSETS = np.asarray((3, 4), dtype=int)
SCHEDULES = (
    (8, 35), (11, 41), (14, 47), (17, 53), (20, 59),
    (23, 65), (29, 71), (35, 72), (41, 77), (47, 77),
)
WINDOW_BY_SCHEDULE = {
    schedule: (5, 6, 7, 8, 9)[index % 5] for index, schedule in enumerate(SCHEDULES)
}
RELATIONSHIPS = {
    "primary_lead1": ((1, 10), 1),
    "primary_lead2": ((1, 10), 2),
    "primary_lead3": ((1, 10), 3),
    "spy_lead1": ((0, 0), 1),
    "spy_lead2": ((0, 0), 2),
    "qqq_lead1": ((1, 1), 1),
    "qqq_lead2": ((1, 1), 2),
    "sector_lead1": ((10, 10), 1),
    "cross_anchor": ((10, 1), 1),
    "mixed_anchor": ((0, 10), 2),
}
_MATRIX_CACHE: dict[tuple, np.ndarray] = {}


@dataclass(slots=True)
class LeadLagModel:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    window_bars: int
    anchors: tuple[int, int]
    lead_bars: int
    betas: np.ndarray


def _training_betas(cube, decision, anchors):
    train = cube.masks()["train_2022_2023"]
    result = []
    for asset, anchor in zip(ASSETS, anchors, strict=True):
        x = cube.bar_return[train, 1 : decision + 1, anchor].ravel()
        y = cube.bar_return[train, 1 : decision + 1, asset].ravel()
        finite = np.isfinite(x) & np.isfinite(y)
        denominator = float(x[finite] @ x[finite])
        result.append(float(x[finite] @ y[finite]) / denominator if denominator > 0 else 0.0)
    return np.asarray(result)


def _row_corr(left, right):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        left_centered = left - np.nanmean(left, axis=1)[:, None]
        right_centered = right - np.nanmean(right, axis=1)[:, None]
    numerator = np.nansum(left_centered * right_centered, axis=1)
    denominator = np.sqrt(
        np.nansum(left_centered**2, axis=1) * np.nansum(right_centered**2, axis=1)
    )
    return np.divide(
        numerator, denominator, out=np.full(len(left), np.nan), where=denominator > 0
    )


def _lead_lag_matrix(cube, model):
    key = (
        id(cube), model.family, model.decision, model.exit_bar, model.window_bars,
        model.anchors, model.lead_bars,
    )
    if key in _MATRIX_CACHE:
        return _MATRIX_CACHE[key]
    pieces = []
    end = model.decision + 1
    start = max(1, end - model.window_bars)
    prior_start = max(1, start - model.window_bars)
    for position, (asset, anchor) in enumerate(
        zip(ASSETS, model.anchors, strict=True)
    ):
        asset_recent = cube.bar_return[:, start:end, asset]
        anchor_recent = cube.bar_return[:, start:end, anchor]
        asset_prior = cube.bar_return[:, prior_start:start, asset]
        anchor_prior = cube.bar_return[:, prior_start:start, anchor]
        corr = _row_corr(asset_recent, anchor_recent)
        prior_corr = _row_corr(asset_prior, anchor_prior)
        lead = model.lead_bars
        lead_corr = _row_corr(asset_recent[:, lead:], anchor_recent[:, :-lead])
        residual = np.nansum(
            asset_recent - model.betas[position] * anchor_recent, axis=1
        )
        anchor_shock = np.nansum(anchor_recent[:, -lead:], axis=1)
        pieces.append(
            np.stack(
                (
                    corr,
                    corr - prior_corr,
                    lead_corr,
                    residual,
                    anchor_shock,
                    residual * anchor_shock,
                ),
                axis=1,
            )
        )
    matrix = np.stack(pieces, axis=1)
    _MATRIX_CACHE[key] = matrix
    return matrix


def _fit(cube, family, schedule):
    anchors, lead_bars = RELATIONSHIPS[family]
    decision, exit_bar = schedule
    window_bars = WINDOW_BY_SCHEDULE[schedule]
    betas = _training_betas(cube, decision, anchors)
    shell = LeadLagModel(
        family, ("corr", "corr_change", "lead_corr", "residual", "anchor_shock", "interaction"),
        decision, exit_bar, np.empty(0), np.empty(0), np.empty(0), window_bars,
        anchors, lead_bars, betas,
    )
    matrix = _lead_lag_matrix(cube, shell)
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
    matrix = _lead_lag_matrix(cube, model)
    score = np.einsum(
        "saf,f->sa", (matrix - model.mean) / model.scale, model.coefficients
    )
    return np.where(np.isfinite(matrix).all(axis=2), score, -np.inf)


def _configure() -> None:
    base.FIRST_VERSION = FIRST_VERSION
    base.LAST_VERSION = LAST_VERSION
    base.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    base.ASSETS = ASSETS
    base.FACTOR_SETS = RELATIONSHIPS
    base.SCHEDULES = SCHEDULES
    base.TOP_K = (1,)
    base.QUANTILES = (0.0, 0.20, 0.40, 0.60, 0.80)
    base.TARGETS = (0.25, 0.40)
    base.MECHANISM = "causal_cross_asset_correlation_break_lead_lag_alpha"
    base.DEFINITION_EXTRA = lambda model: {
        "anchors": list(model.anchors),
        "lead_bars": model.lead_bars,
        "lead_minutes": model.lead_bars * 5,
        "window_bars": model.window_bars,
        "feature_transform": "training_beta_residual_and_causal_lead_lag",
        "training_target": "asset_return_minus_spy_return",
    }
    base._fit = _fit
    base._scores = _scores


if __name__ == "__main__":
    _configure()
    base.main()
