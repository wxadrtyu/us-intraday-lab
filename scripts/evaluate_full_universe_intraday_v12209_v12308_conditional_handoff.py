"""Conditional same-day continuation or rotation after an observed first leg."""

from __future__ import annotations

from dataclasses import dataclass

import evaluate_full_universe_intraday_v12009_v12108_topk_cross_section as base
import numpy as np

FIRST_VERSION = 12209
LAST_VERSION = 12308
PRIOR_COMPARISON_CELLS = 315_583
BASE_FAMILIES = (
    "trend_flow_state",
    "trend_structure",
    "reclaim_flow",
    "contraction_breakout",
    "relative_leadership",
)
POLICIES = ("continue_if_confirmed", "switch_if_failed")
FACTOR_SETS = {
    f"{family}__{policy}": (family, policy)
    for family in BASE_FAMILIES
    for policy in POLICIES
}
HANDOFF_SCHEDULES = (
    (2, 11, 23),
    (2, 17, 35),
    (5, 23, 41),
    (8, 29, 47),
    (11, 35, 53),
    (17, 41, 59),
    (23, 47, 65),
    (29, 53, 71),
    (35, 59, 77),
    (41, 65, 77),
)
SCHEDULES = tuple((decision, final) for decision, _handoff, final in HANDOFF_SCHEDULES)
HANDOFF_BY_SCHEDULE = {
    (decision, final): handoff for decision, handoff, final in HANDOFF_SCHEDULES
}


@dataclass(slots=True)
class HandoffModel:
    family: str
    factors: tuple[str, ...]
    decision: int
    exit_bar: int
    mean: np.ndarray
    scale: np.ndarray
    coefficients: np.ndarray
    parent: object
    handoff_bar: int
    policy: str


def _fit(cube, family, schedule):
    base_family, policy = FACTOR_SETS[family]
    handoff = HANDOFF_BY_SCHEDULE[schedule]
    parent = base.residual._fit(
        cube, base_family, (schedule[0], handoff), 0.0, base.ALPHA
    )
    return HandoffModel(
        family,
        parent.factors,
        int(schedule[0]),
        int(schedule[1]),
        parent.mean,
        parent.scale,
        parent.coefficients,
        parent,
        handoff,
        policy,
    )


def _scores(cube, model):
    matrix = base.residual._matrix(cube, model.parent.factors, model.decision)
    score = np.einsum(
        "saf,f->sa",
        (matrix - model.parent.mean) / model.parent.scale,
        model.parent.coefficients,
    )
    return np.where(np.isfinite(matrix).all(axis=2), score, -np.inf)


def _raw(cube, model, _top_k, threshold, cost, delay):
    score = _scores(cube, model)
    local = np.argmax(score, axis=1)
    selected = base.ASSETS[local]
    best = score[cube.rows, local]
    first_entry = model.decision + 1 + delay
    handoff = model.handoff_bar
    second_entry = handoff + 1 + delay
    final = model.exit_bar
    rows = cube.rows
    first_active = np.isfinite(best) & (best >= threshold)
    first_active &= cube.first[rows, first_entry, selected] <= first_entry * 5
    first_active &= cube.first[rows, handoff, selected] <= handoff * 5
    first_active &= np.isfinite(cube.opens[rows, first_entry, selected])
    first_active &= np.isfinite(cube.opens[rows, handoff, selected])
    first_active &= np.isfinite(cube.opens[:, first_entry, 0])
    first_active &= np.isfinite(cube.opens[:, handoff, 0])
    observed_relative = (
        cube.opens[rows, handoff, selected] / cube.opens[rows, first_entry, selected]
        - cube.opens[:, handoff, 0] / cube.opens[:, first_entry, 0]
    )
    if model.policy == "continue_if_confirmed":
        second_selected = selected
        condition = observed_relative > 0
    else:
        second_selected = base.ASSETS[1 - local]
        condition = observed_relative <= 0
    second_active = first_active & condition
    second_active &= cube.first[rows, second_entry, second_selected] <= second_entry * 5
    second_active &= cube.first[rows, final, second_selected] <= final * 5
    second_active &= np.isfinite(cube.opens[rows, second_entry, second_selected])
    second_active &= np.isfinite(cube.opens[rows, final, second_selected])
    second_active &= np.isfinite(cube.opens[:, second_entry, 0])
    second_active &= np.isfinite(cube.opens[:, final, 0])
    values = np.zeros(len(cube.sessions))
    benchmark = np.zeros(len(cube.sessions))
    values[first_active] = (
        cube.opens[rows[first_active], handoff, selected[first_active]]
        / cube.opens[rows[first_active], first_entry, selected[first_active]]
        - 1.0
        - cost
    )
    benchmark[first_active] = (
        cube.opens[first_active, handoff, 0] / cube.opens[first_active, first_entry, 0] - 1.0
    )
    values[second_active] += (
        cube.opens[rows[second_active], final, second_selected[second_active]]
        / cube.opens[rows[second_active], second_entry, second_selected[second_active]]
        - 1.0
        - cost
    )
    benchmark[second_active] += (
        cube.opens[second_active, final, 0] / cube.opens[second_active, second_entry, 0] - 1.0
    )
    return base.v34.v12.ReturnStream(
        values,
        benchmark,
        first_active,
        first_active.astype(int) + second_active.astype(int),
    )


def _definition_extra(model):
    return {
        "first_leg_exit_bar": model.handoff_bar,
        "second_leg_entry_bar": model.handoff_bar + 1,
        "handoff_policy": model.policy,
    }


def _configure() -> None:
    base.FIRST_VERSION = FIRST_VERSION
    base.LAST_VERSION = LAST_VERSION
    base.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    base.ASSETS = np.asarray((3, 4), dtype=int)
    base.FACTOR_SETS = FACTOR_SETS
    base.SCHEDULES = SCHEDULES
    base.TOP_K = (1,)
    base.QUANTILES = (0.0, 0.25, 0.50)
    base.TARGETS = (0.25, 0.40)
    base.MECHANISM = "conditional_intraday_handoff"
    base.DEFINITION_EXTRA = _definition_extra
    base._fit = _fit
    base._scores = _scores
    base._raw = _raw


if __name__ == "__main__":
    _configure()
    base.main()
