"""Asset-specific leveraged ETF intraday residual-alpha models."""

from __future__ import annotations

from dataclasses import dataclass

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import numpy as np

FIRST_VERSION = 12609
LAST_VERSION = 12708
PRIOR_COMPARISON_CELLS = 319_183
ASSETS = np.asarray((3, 4), dtype=int)


@dataclass(slots=True)
class AssetSpecificModel:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray


def _fit(cube, family, schedule):
    factors = base.residual.FACTOR_SETS[family]
    decision, exit_bar = schedule
    entry = decision + 1
    matrix = base._matrix(cube, factors, decision)
    asset_return = cube.opens[:, exit_bar, ASSETS] / cube.opens[:, entry, ASSETS] - 1.0
    spy_return = cube.opens[:, exit_bar, 0] / cube.opens[:, entry, 0] - 1.0
    target = asset_return - spy_return[:, None]
    quality = (
        (cube.first[:, entry, ASSETS] <= entry * 5)
        & (cube.first[:, exit_bar, ASSETS] <= exit_bar * 5)
        & np.isfinite(matrix).all(axis=2)
        & np.isfinite(target)
    )
    train_days = cube.masks()["train_2022_2023"]
    means = np.zeros((len(ASSETS), len(factors)))
    scales = np.ones_like(means)
    coefficients = np.zeros_like(means)
    for local in range(len(ASSETS)):
        use = train_days & quality[:, local]
        values, labels = matrix[use, local], target[use, local]
        means[local] = values.mean(axis=0)
        scales[local] = values.std(axis=0)
        scales[local, scales[local] < 1e-8] = 1.0
        standardized = (values - means[local]) / scales[local]
        coefficients[local] = np.linalg.solve(
            standardized.T @ standardized + base.ALPHA * np.eye(len(factors)),
            standardized.T @ labels,
        )
    return AssetSpecificModel(
        family,
        factors,
        int(decision),
        int(exit_bar),
        means,
        scales,
        coefficients,
    )


def _scores(cube, model):
    matrix = base._matrix(cube, model.factors, model.decision)
    standardized = (matrix - model.mean[None, :, :]) / model.scale[None, :, :]
    score = np.einsum("saf,af->sa", standardized, model.coefficients)
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
    base.MECHANISM = "asset_specific_residual_alpha"
    base.DEFINITION_EXTRA = lambda _model: {
        "training_target": "asset_return_minus_spy_return",
        "coefficient_contract": "separate_train_only_ridge_per_asset",
    }
    base._fit = _fit
    base._scores = _scores


if __name__ == "__main__":
    _configure()
    base.main()
