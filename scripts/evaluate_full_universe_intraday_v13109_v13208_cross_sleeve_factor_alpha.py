"""Joint-gated triple windows with complementary factor families."""

from __future__ import annotations

from dataclasses import dataclass

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import evaluate_full_universe_intraday_v12709_v12808_dual_window_alpha as shared
import numpy as np

FIRST_VERSION = 13109
LAST_VERSION = 13208
PRIOR_COMPARISON_CELLS = 324_183
ASSETS = np.asarray((3, 4), dtype=int)
WINDOWS = ((2, 23), (23, 47), (47, 77))
FAMILIES = tuple(base.residual.FACTOR_SETS)
VARIANTS = tuple(range(10))


@dataclass(slots=True)
class CrossSleeveFactorModel:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    sleeves: tuple[base.Model, ...]
    sleeve_families: tuple[str, ...]


def _family_triple(first_family, variant):
    first = FAMILIES.index(first_family)
    return (
        FAMILIES[first],
        FAMILIES[variant],
        FAMILIES[(first + 3 * variant + 1) % len(FAMILIES)],
    )


def _fit(cube, first_family, variant):
    sleeve_families = _family_triple(first_family, variant)
    sleeves = tuple(
        shared.ORIGINAL_FIT(cube, family, schedule)
        for family, schedule in zip(sleeve_families, WINDOWS, strict=True)
    )
    return CrossSleeveFactorModel(
        family="|".join(sleeve_families),
        factors=tuple(
            f"sleeve_{index}:{factor}"
            for index, sleeve in enumerate(sleeves)
            for factor in sleeve.factors
        ),
        decision=sleeves[0].decision,
        exit_bar=sleeves[-1].exit_bar,
        mean=np.concatenate([model.mean for model in sleeves]),
        scale=np.concatenate([model.scale for model in sleeves]),
        coefficients=np.concatenate([model.coefficients for model in sleeves]),
        sleeves=sleeves,
        sleeve_families=sleeve_families,
    )


def _sleeve_scores(cube, model):
    return tuple(shared.ORIGINAL_SCORES(cube, sleeve) for sleeve in model.sleeves)


def _scores(cube, model):
    return np.mean(np.stack(_sleeve_scores(cube, model)), axis=0)


def _raw(cube, model, top_k, threshold, cost, delay):
    scores = _sleeve_scores(cube, model)
    aggregates = [
        np.mean(np.partition(score, -top_k, axis=1)[:, -top_k:], axis=1)
        for score in scores
    ]
    joint_score = np.mean(np.stack(aggregates), axis=0)
    joint_active = np.isfinite(joint_score) & (joint_score >= threshold)
    sleeve_streams = tuple(
        shared._single_raw(cube, sleeve, top_k, cost, delay)
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
        "sleeve_windows": [list(window) for window in WINDOWS],
        "sleeve_factor_families": list(model.sleeve_families),
        "capital_reuse": "sequential_full_gross_non_overlapping",
        "daily_gate": "mean_of_three_sleeve_cross_sectional_scores",
        "factor_design": "preregistered_latin_cross_sleeve_combinations",
    }


def _configure() -> None:
    base.FIRST_VERSION = FIRST_VERSION
    base.LAST_VERSION = LAST_VERSION
    base.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    base.ASSETS = ASSETS
    base.FACTOR_SETS = FAMILIES
    base.SCHEDULES = VARIANTS
    base.TOP_K = (1,)
    base.QUANTILES = (0.0, 0.20, 0.40, 0.60, 0.80)
    base.TARGETS = (0.25, 0.40)
    base.MECHANISM = "joint_gated_cross_sleeve_factor_alpha"
    base.DEFINITION_EXTRA = _definition_extra
    base._fit = _fit
    base._scores = _scores
    base._streams = _streams


if __name__ == "__main__":
    _configure()
    base.main()
