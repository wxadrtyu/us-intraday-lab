"""Two non-overlapping intraday residual-alpha sleeves per session."""

from __future__ import annotations

from dataclasses import dataclass

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import numpy as np

FIRST_VERSION = 12709
LAST_VERSION = 12808
PRIOR_COMPARISON_CELLS = 320_183
ASSETS = np.asarray((3, 4), dtype=int)
WINDOW_PAIRS = (
    ((2, 23), (29, 65)),
    ((2, 23), (35, 71)),
    ((5, 29), (35, 71)),
    ((5, 29), (41, 72)),
    ((8, 35), (41, 72)),
    ((8, 35), (47, 77)),
    ((11, 47), (47, 77)),
    ((11, 41), (47, 72)),
    ((17, 47), (47, 77)),
    ((17, 53), (53, 77)),
)
ORIGINAL_FIT = base._fit
ORIGINAL_SCORES = base._scores
ORIGINAL_RAW = base._raw


@dataclass(slots=True)
class DualWindowModel:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    sleeves: tuple[base.Model, base.Model]


def _fit(cube, family, schedule_pair):
    sleeves = tuple(ORIGINAL_FIT(cube, family, schedule) for schedule in schedule_pair)
    return DualWindowModel(
        family=family,
        factors=sleeves[0].factors,
        decision=sleeves[0].decision,
        exit_bar=sleeves[1].exit_bar,
        mean=np.stack([model.mean for model in sleeves]),
        scale=np.stack([model.scale for model in sleeves]),
        coefficients=np.stack([model.coefficients for model in sleeves]),
        sleeves=sleeves,
    )


def _sleeve_scores(cube, model):
    return tuple(ORIGINAL_SCORES(cube, sleeve) for sleeve in model.sleeves)


def _scores(cube, model):
    scores = _sleeve_scores(cube, model)
    return np.mean(np.stack(scores), axis=0)


def _raw(cube, model, top_k, threshold, cost, delay):
    scores = _sleeve_scores(cube, model)
    aggregates = [
        np.mean(np.partition(score, -top_k, axis=1)[:, -top_k:], axis=1)
        for score in scores
    ]
    joint_score = np.mean(np.stack(aggregates), axis=0)
    joint_active = np.isfinite(joint_score) & (joint_score >= threshold)
    sleeve_streams = tuple(
        ORIGINAL_RAW(cube, sleeve, top_k, -np.inf, cost, delay)
        for sleeve in model.sleeves
    )
    valid = joint_active & np.logical_and.reduce([stream.active for stream in sleeve_streams])
    values = np.sum([stream.values for stream in sleeve_streams], axis=0)
    benchmark = np.sum([stream.benchmark for stream in sleeve_streams], axis=0)
    component_trades = np.sum(
        [stream.component_trades for stream in sleeve_streams], axis=0
    )
    return base.v34.v12.ReturnStream(
        np.where(valid, values, 0.0),
        np.where(valid, benchmark, 0.0),
        valid,
        np.where(valid, component_trades, 0).astype(int),
    )


def _streams(cube, model, top_k, threshold, target):
    raw = tuple(
        _raw(cube, model, top_k, threshold, cost, delay)
        for cost, delay in (
            (base.v34.STANDARD_COST, 0),
            (base.v34.STRESS_COST, 0),
            (base.v34.STANDARD_COST, 1),
        )
    )
    exposure = base.v42._exposure(raw[0].values, 20, target, 0.0)
    return tuple(base.v42._scaled(stream, exposure) for stream in raw)


def _definition_extra(model):
    return {
        "sleeve_windows": [
            [sleeve.decision, sleeve.exit_bar] for sleeve in model.sleeves
        ],
        "capital_reuse": "sequential_full_gross_non_overlapping",
        "daily_gate": "mean_of_two_sleeve_cross_sectional_scores",
    }


def _configure() -> None:
    base.FIRST_VERSION = FIRST_VERSION
    base.LAST_VERSION = LAST_VERSION
    base.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    base.ASSETS = ASSETS
    base.FACTOR_SETS = base.residual.FACTOR_SETS
    base.SCHEDULES = WINDOW_PAIRS
    base.TOP_K = (1,)
    base.QUANTILES = (0.0, 0.20, 0.40, 0.60, 0.80)
    base.TARGETS = (0.25, 0.40)
    base.MECHANISM = "non_overlapping_dual_window_residual_alpha"
    base.DEFINITION_EXTRA = _definition_extra
    base._fit = _fit
    base._scores = _scores
    base._streams = _streams


if __name__ == "__main__":
    _configure()
    base.main()
