"""Independently activated non-overlapping intraday alpha sleeves."""

from __future__ import annotations

from dataclasses import dataclass

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import evaluate_full_universe_intraday_v12709_v12808_dual_window_alpha as shared
import evaluate_full_universe_intraday_v12809_v12908_triple_window_alpha as triple
import numpy as np

FIRST_VERSION = 13009
LAST_VERSION = 13108
PRIOR_COMPARISON_CELLS = 323_183
ASSETS = np.asarray((3, 4), dtype=int)
WINDOW_TRIPLES = triple.WINDOW_TRIPLES


@dataclass(slots=True)
class IndependentSleeveModel:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    sleeves: tuple[base.Model, ...]


def _fit(cube, family, schedule_group):
    sleeves = tuple(
        shared.ORIGINAL_FIT(cube, family, schedule) for schedule in schedule_group
    )
    return IndependentSleeveModel(
        family=family,
        factors=sleeves[0].factors,
        decision=sleeves[0].decision,
        exit_bar=sleeves[-1].exit_bar,
        mean=np.stack([model.mean for model in sleeves]),
        scale=np.stack([model.scale for model in sleeves]),
        coefficients=np.stack([model.coefficients for model in sleeves]),
        sleeves=sleeves,
    )


def _scores(cube, model):
    return np.stack(
        [shared.ORIGINAL_SCORES(cube, sleeve) for sleeve in model.sleeves]
    )


def _threshold(cube, scores, top_k, quantile):
    train = cube.masks()["train_2022_2023"]
    thresholds = []
    for score in scores:
        aggregate = np.mean(
            np.partition(score, -top_k, axis=1)[:, -top_k:], axis=1
        )
        use = train & np.isfinite(aggregate)
        thresholds.append(float(np.quantile(aggregate[use], quantile)))
    return tuple(thresholds)


def _raw(cube, model, top_k, thresholds, cost, delay):
    values = np.zeros(len(cube.sessions))
    benchmark = np.zeros(len(cube.sessions))
    component_trades = np.zeros(len(cube.sessions), dtype=int)
    active = np.zeros(len(cube.sessions), dtype=bool)
    for sleeve, threshold in zip(model.sleeves, thresholds, strict=True):
        score = shared.ORIGINAL_SCORES(cube, sleeve)
        aggregate = np.mean(
            np.partition(score, -top_k, axis=1)[:, -top_k:], axis=1
        )
        raw = shared._single_raw(cube, sleeve, top_k, cost, delay)
        sleeve_active = raw.active & np.isfinite(aggregate) & (aggregate >= threshold)
        values[sleeve_active] += raw.values[sleeve_active]
        benchmark[sleeve_active] += raw.benchmark[sleeve_active]
        component_trades[sleeve_active] += raw.component_trades[sleeve_active]
        active |= sleeve_active
    return base.v34.v12.ReturnStream(values, benchmark, active, component_trades)


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
        "activation": "independent_train_fixed_threshold_per_sleeve",
    }


def _configure() -> None:
    base.FIRST_VERSION = FIRST_VERSION
    base.LAST_VERSION = LAST_VERSION
    base.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    base.ASSETS = ASSETS
    base.FACTOR_SETS = base.residual.FACTOR_SETS
    base.SCHEDULES = WINDOW_TRIPLES
    base.TOP_K = (1,)
    base.QUANTILES = (0.0, 0.20, 0.40, 0.60, 0.80)
    base.TARGETS = (0.25, 0.40)
    base.MECHANISM = "independently_activated_triple_window_residual_alpha"
    base.DEFINITION_EXTRA = _definition_extra
    base._fit = _fit
    base._scores = _scores
    base._threshold = _threshold
    base._streams = _streams


if __name__ == "__main__":
    _configure()
    base.main()
