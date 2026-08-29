"""Robust-missingness extension of the frozen concentration campaign."""

from __future__ import annotations

from pathlib import Path

import evaluate_full_universe_intraday_v1966_v2065_concentration_risk as base
import numpy as np

PROPOSAL = Path(__file__).resolve().parents[1] / (
    "research/proposals/full_universe_intraday_v2066_v2165_robust_concentration/proposal.json"
)
MINIMUM_OBSERVED = 12


def _design(matrix, imputation):
    observed = np.isfinite(matrix)
    eligible = observed.sum(axis=1) >= MINIMUM_OBSERVED
    filled = np.where(observed, matrix, imputation)
    return np.column_stack((filled, (~observed).astype(float))), eligible


def fit_prediction(cube, target, alpha=10.0):
    matrix, names = base.factor_matrix(cube)
    train = cube.masks()["train_2022_2023"]
    imputation = np.nanmedian(matrix[train], axis=0)
    design, eligible = _design(matrix, imputation)
    valid = train & eligible & np.isfinite(target)
    values, labels = design[valid], target[valid]
    mean, scale = values.mean(axis=0), values.std(axis=0)
    scale[scale < 1e-8] = 1.0
    standardized = (values - mean) / scale
    intercept = float(labels.mean())
    coefficients = np.linalg.solve(
        standardized.T @ standardized + alpha * np.eye(standardized.shape[1]),
        standardized.T @ (labels - intercept),
    )
    prediction = np.full(len(matrix), np.nan)
    prediction[eligible] = intercept + ((design[eligible] - mean) / scale) @ coefficients
    model = {
        "factor_names": names + tuple(f"missing_{name}" for name in names),
        "raw_factor_names": names,
        "imputation": imputation.tolist(),
        "minimum_observed": MINIMUM_OBSERVED,
        "mean": mean.tolist(),
        "scale": scale.tolist(),
        "coefficients": coefficients.tolist(),
        "intercept": intercept,
        "alpha": alpha,
    }
    return prediction, model


def predict(cube, model):
    matrix, names = base.factor_matrix(cube)
    if tuple(model["raw_factor_names"]) != names:
        raise ValueError("RAW_FACTOR_IDENTITY_MISMATCH")
    design, eligible = _design(matrix, np.asarray(model["imputation"]))
    output = np.full(len(matrix), np.nan)
    output[eligible] = model["intercept"] + (
        (design[eligible] - np.asarray(model["mean"])) / np.asarray(model["scale"])
    ) @ np.asarray(model["coefficients"])
    return output


if __name__ == "__main__":
    base.PROPOSAL = PROPOSAL
    base.CODE_PATH = Path(__file__)
    base.fit_prediction = fit_prediction
    base.predict = predict
    base.main()
