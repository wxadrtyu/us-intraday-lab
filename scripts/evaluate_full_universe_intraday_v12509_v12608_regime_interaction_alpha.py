"""Train-fixed market-state interaction alpha for leveraged intraday ETFs."""

from __future__ import annotations

from dataclasses import dataclass

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import numpy as np

FIRST_VERSION = 12509
LAST_VERSION = 12608
PRIOR_COMPARISON_CELLS = 318_183
ASSETS = np.asarray((3, 4), dtype=int)


@dataclass(slots=True)
class RegimeInteractionModel:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    market_return_cut: float
    market_volatility_cut: float


def _regime_inputs(cube, decision):
    available = cube.factors(decision)
    return available["current_return"][:, 0], available["spy_volatility"][:, 0]


def _expanded_matrix(cube, factors, decision, return_cut, volatility_cut):
    matrix = base._matrix(cube, factors, decision)
    market_return, market_volatility = _regime_inputs(cube, decision)
    regimes = (
        (market_return >= return_cut).astype(int) * 2
        + (market_volatility >= volatility_cut).astype(int)
    )
    one_hot = np.eye(4, dtype=float)[regimes]
    interactions = matrix[:, :, :, None] * one_hot[:, None, None, :]
    return np.concatenate((matrix, interactions.reshape(*matrix.shape[:2], -1)), axis=2)


def _fit(cube, family, schedule):
    factors = base.residual.FACTOR_SETS[family]
    decision, exit_bar = schedule
    entry = decision + 1
    train_days = cube.masks()["train_2022_2023"]
    market_return, market_volatility = _regime_inputs(cube, decision)
    return_cut = float(np.nanmedian(market_return[train_days]))
    volatility_cut = float(np.nanmedian(market_volatility[train_days]))
    matrix = _expanded_matrix(
        cube, factors, decision, return_cut, volatility_cut
    )
    asset_return = cube.opens[:, exit_bar, ASSETS] / cube.opens[:, entry, ASSETS] - 1.0
    spy_return = cube.opens[:, exit_bar, 0] / cube.opens[:, entry, 0] - 1.0
    target = asset_return - spy_return[:, None]
    quality = (
        (cube.first[:, entry, ASSETS] <= entry * 5)
        & (cube.first[:, exit_bar, ASSETS] <= exit_bar * 5)
        & np.isfinite(matrix).all(axis=2)
        & np.isfinite(target)
    )
    train = train_days[:, None] & quality
    values, labels = matrix[train], target[train]
    mean, scale = values.mean(axis=0), values.std(axis=0)
    scale[scale < 1e-8] = 1.0
    standardized = (values - mean) / scale
    coefficients = np.linalg.solve(
        standardized.T @ standardized + base.ALPHA * np.eye(standardized.shape[1]),
        standardized.T @ labels,
    )
    return RegimeInteractionModel(
        family,
        factors,
        int(decision),
        int(exit_bar),
        mean,
        scale,
        coefficients,
        return_cut,
        volatility_cut,
    )


def _scores(cube, model):
    matrix = _expanded_matrix(
        cube,
        model.factors,
        model.decision,
        model.market_return_cut,
        model.market_volatility_cut,
    )
    score = np.einsum(
        "saf,f->sa", (matrix - model.mean) / model.scale, model.coefficients
    )
    return np.where(np.isfinite(matrix).all(axis=2), score, -np.inf)


def _definition_extra(model):
    return {
        "training_target": "asset_return_minus_spy_return",
        "regime_definition": "train_fixed_2x2_market_return_and_volatility_state",
        "market_return_cut": model.market_return_cut,
        "market_volatility_cut": model.market_volatility_cut,
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
    base.MECHANISM = "train_fixed_market_state_interaction_alpha"
    base.DEFINITION_EXTRA = _definition_extra
    base._fit = _fit
    base._scores = _scores


if __name__ == "__main__":
    _configure()
    base.main()
