"""Monotonic market-health score plus same-symbol concentration cap."""

from __future__ import annotations

from pathlib import Path

import evaluate_full_universe_intraday_v1966_v2065_concentration_risk as base
import numpy as np

PROPOSAL = Path(__file__).resolve().parents[1] / (
    "research/proposals/full_universe_intraday_v2166_v2265_monotonic_risk/proposal.json"
)
INDICES = np.array((0, 1, 2, 3, 4, 8, 14))
DIRECTIONS = np.array((1.0, -1.0, 1.0, -1.0, 1.0, 1.0, 1.0))
MINIMUM_OBSERVED = 5


def _raw(cube):
    matrix, names = base.factor_matrix(cube)
    return matrix[:, INDICES], tuple(names[i] for i in INDICES)


def _score(matrix, model):
    observed = np.isfinite(matrix)
    eligible = observed.sum(axis=1) >= model["minimum_observed"]
    filled = np.where(observed, matrix, model["imputation"])
    score = np.full(len(matrix), np.nan)
    score[eligible] = np.mean(
        (filled[eligible] - model["mean"]) / model["scale"] * model["directions"], axis=1
    )
    return score


def fit_prediction(cube, target, alpha=10.0):
    del target, alpha
    matrix, names = _raw(cube)
    train = cube.masks()["train_2022_2023"]
    imputation = np.nanmedian(matrix[train], axis=0)
    filled = np.where(np.isfinite(matrix[train]), matrix[train], imputation)
    mean, scale = np.mean(filled, axis=0), np.std(filled, axis=0)
    scale[scale < 1e-8] = 1.0
    model = {
        "raw_factor_names": names,
        "imputation": imputation.tolist(),
        "minimum_observed": MINIMUM_OBSERVED,
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "directions": DIRECTIONS.tolist(),
        "method": "equal_weight_monotonic_zscore",
    }
    return _score(matrix, model), model


def predict(cube, model):
    matrix, names = _raw(cube)
    if tuple(model["raw_factor_names"]) != names:
        raise ValueError("RAW_FACTOR_IDENTITY_MISMATCH")
    return _score(matrix, model)


if __name__ == "__main__":
    base.PROPOSAL = PROPOSAL
    base.CODE_PATH = Path(__file__)
    base.fit_prediction = fit_prediction
    base.predict = predict
    base.main()
