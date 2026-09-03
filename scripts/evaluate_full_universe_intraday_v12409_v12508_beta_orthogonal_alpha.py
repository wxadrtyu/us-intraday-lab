"""Train-fixed market-beta orthogonalized leveraged intraday alpha."""

from __future__ import annotations

from dataclasses import dataclass

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import numpy as np

FIRST_VERSION = 12409
LAST_VERSION = 12508
PRIOR_COMPARISON_CELLS = 317_183
ASSETS = np.asarray((3, 4), dtype=int)


@dataclass(slots=True)
class OrthogonalModel:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    market_beta: np.ndarray


def _fit(cube, family, schedule):
    factors = base.residual.FACTOR_SETS[family]
    decision, exit_bar = schedule
    entry = decision + 1
    matrix = base.residual._matrix(cube, factors, decision)
    asset_return = cube.opens[:, exit_bar, ASSETS] / cube.opens[:, entry, ASSETS] - 1.0
    market_return = cube.opens[:, exit_bar, 0] / cube.opens[:, entry, 0] - 1.0
    quality = (
        (cube.first[:, entry, ASSETS] <= entry * 5)
        & (cube.first[:, exit_bar, ASSETS] <= exit_bar * 5)
        & np.isfinite(matrix).all(axis=2)
        & np.isfinite(asset_return)
        & np.isfinite(market_return[:, None])
    )
    train_days = cube.masks()["train_2022_2023"]
    betas = np.zeros(len(ASSETS))
    for local in range(len(ASSETS)):
        use = train_days & quality[:, local]
        market = market_return[use]
        variance = float(np.dot(market, market))
        betas[local] = (
            float(np.dot(market, asset_return[use, local])) / variance
            if variance > 1e-12
            else 0.0
        )
    target = asset_return - market_return[:, None] * betas
    train = train_days[:, None] & quality
    values, labels = matrix[train], target[train]
    mean, scale = values.mean(axis=0), values.std(axis=0)
    scale[scale < 1e-8] = 1.0
    standardized = (values - mean) / scale
    coefficients = np.linalg.solve(
        standardized.T @ standardized + base.ALPHA * np.eye(len(factors)),
        standardized.T @ labels,
    )
    return OrthogonalModel(
        family,
        factors,
        int(decision),
        int(exit_bar),
        mean,
        scale,
        coefficients,
        betas,
    )


def _definition_extra(model):
    return {
        "training_target": "asset_return_minus_fixed_beta_times_spy_return",
        "train_fixed_market_beta": model.market_beta.tolist(),
    }


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
    base.MECHANISM = "train_fixed_market_beta_orthogonal_alpha"
    base.DEFINITION_EXTRA = _definition_extra
    base._fit = _fit


if __name__ == "__main__":
    _configure()
    base.main()
