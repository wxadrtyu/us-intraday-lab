"""Conditional exits plus a training-fitted 16-factor tail-severity overlay."""

from __future__ import annotations

from pathlib import Path

import evaluate_full_universe_intraday_v1966_v2065_concentration_risk as factors
import evaluate_full_universe_intraday_v2266_v2365_post_entry_risk as base
import evaluate_full_universe_intraday_v2366_v2465_conditional_exit as conditional
import numpy as np

PROPOSAL = Path(__file__).resolve().parents[1] / (
    "research/proposals/full_universe_intraday_v2666_v2765_tail_risk_model/proposal.json"
)
ORIGINAL_BUILD_STREAMS = base.build_streams
MINIMUM_OBSERVED = 12
_MODEL_CACHE: dict[int, tuple[dict, np.ndarray]] = {}


def mode_parameters(mode: str) -> tuple[float, float]:
    prefix = "tail_cap_"
    if not mode.startswith(prefix) or "_q_" not in mode:
        raise ValueError("UNKNOWN_TAIL_RISK_MODE")
    cap_text, quantile_text = mode.removeprefix(prefix).split("_q_", maxsplit=1)
    cap, quantile = float(cap_text), float(quantile_text)
    if not 0 < cap <= 1 or not 0 < quantile < 1:
        raise ValueError("TAIL_RISK_PARAMETER_OUT_OF_RANGE")
    return cap, quantile


def fit_model(development) -> tuple[dict, np.ndarray]:
    matrix, names = factors.factor_matrix(development)
    baseline = next(
        base.risk.add(left, right)
        for left, right in base.risk.baseline_parts(development, development)
    )
    target = np.maximum(-baseline.values, 0.0) ** 2
    observed = np.isfinite(matrix)
    train = development.masks()["train_2022_2023"]
    imputation = np.nanmedian(matrix[train], axis=0)
    filled = np.where(observed, matrix, imputation)
    eligible = observed.sum(axis=1) >= MINIMUM_OBSERVED
    valid = train & eligible & np.isfinite(target)
    mean, scale = filled[valid].mean(axis=0), filled[valid].std(axis=0)
    scale[scale < 1e-8] = 1.0
    x = (filled[valid] - mean) / scale
    intercept = float(target[valid].mean())
    coefficients = np.linalg.solve(
        x.T @ x + 10.0 * np.eye(x.shape[1]), x.T @ (target[valid] - intercept)
    )
    model = {
        "factor_names": names,
        "imputation": imputation,
        "mean": mean,
        "scale": scale,
        "coefficients": coefficients,
        "intercept": intercept,
        "minimum_observed": MINIMUM_OBSERVED,
    }
    score, _ = predict(development, model)
    return model, score


def predict(cube, model) -> tuple[np.ndarray, np.ndarray]:
    matrix, names = factors.factor_matrix(cube)
    if tuple(model["factor_names"]) != names:
        raise ValueError("TAIL_FACTOR_IDENTITY_MISMATCH")
    observed = np.isfinite(matrix)
    eligible = observed.sum(axis=1) >= model["minimum_observed"]
    filled = np.where(observed, matrix, model["imputation"])
    score = np.full(len(matrix), np.nan)
    score[eligible] = model["intercept"] + (
        (filled[eligible] - model["mean"]) / model["scale"]
    ) @ model["coefficients"]
    return score, eligible


def scores(cube, development) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    key = id(development)
    cached = _MODEL_CACHE.get(key)
    if cached is None:
        cached = fit_model(development)
        _MODEL_CACHE[key] = cached
    model, development_score = cached
    if cube is development:
        score = development_score
        eligible = np.isfinite(score)
    else:
        score, eligible = predict(cube, model)
    return score, eligible, development_score


def build_streams(cube, development, record, models, definition):
    cap, quantile = mode_parameters(definition["application_mode"])
    stop_definition = {**definition, "application_mode": "both_sleeves"}
    streams, valids, exits = ORIGINAL_BUILD_STREAMS(
        cube, development, record, models, stop_definition
    )
    score, eligible, development_score = scores(cube, development)
    train = development.masks()["train_2022_2023"] & np.isfinite(development_score)
    threshold = float(np.quantile(development_score[train], quantile))
    multiplier = np.where(eligible, np.where(score >= threshold, cap, 1.0), 0.0)
    return (
        tuple(base.risk.scaled(stream, multiplier) for stream in streams),
        tuple(valid & eligible for valid in valids),
        exits,
    )


if __name__ == "__main__":
    base.PROPOSAL = PROPOSAL
    base.CODE_PATH = Path(__file__)
    base.CODE_DEPENDENCIES = (
        Path(base.__file__),
        Path(conditional.__file__),
        Path(factors.__file__),
    )
    base.stopped_raw = conditional.stopped_raw
    base.build_streams = build_streams
    base.main()
