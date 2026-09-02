"""v9605-v9704 causal rebuild of the rejected v9292 late-route idea.

Every frozen v42 parent is repriced no earlier than the first open after the
bar-23 gate.  Parent selection remains frozen at its native decision time and
volatility exposure is recomputed from the repriced standard-cost stream.
"""

from __future__ import annotations

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v35_rank_ensemble as v35
import evaluate_full_universe_intraday_v42_multifactor_vol_target as v42
import evaluate_full_universe_intraday_v9204_v9303_causal_opening_late_soft_veto as parent
import numpy as np


FIRST_VERSION = 9605
LAST_VERSION = 9704
PRIOR_COMPARISON_CELLS = 284_383
GATE_DECISION = 23
MINIMUM_ENTRY_BAR = GATE_DECISION + 1


def effective_entry_bar(decision: int, delay: int) -> int:
    """First executable bar after both the native signal and late gate."""
    return max(int(decision) + 1, MINIMUM_ENTRY_BAR) + int(delay)


def _repriced_sleeve(cube, model, cost: float, delay: int):
    matrix, _, _ = v34._matrix(cube, model.specification, model.factors)
    score = np.einsum(
        "saf,f,f->sa",
        (matrix - model.mean) / model.scale,
        model.direction,
        model.weights,
    )
    score = np.where(np.isfinite(matrix).all(axis=2), score, -np.inf)
    local = np.argmax(score, axis=1)
    assets = np.asarray(model.specification["assets"], dtype=int)
    selected = assets[local]
    value = score[cube.rows, local]
    decision = int(model.specification["decision"])
    entry = effective_entry_bar(decision, delay)
    exit_bar = int(model.specification["exit"])
    active = np.isfinite(value) & (value >= model.threshold) & (entry < exit_bar)
    active &= cube.first[cube.rows, entry, selected] <= entry * 5 + cube.boundary_tolerance
    active &= cube.first[cube.rows, exit_bar, selected] <= exit_bar * 5 + cube.boundary_tolerance
    active &= np.isfinite(cube.opens[cube.rows, entry, selected])
    active &= np.isfinite(cube.opens[cube.rows, exit_bar, selected])
    active &= np.isfinite(cube.opens[:, entry, 0])
    active &= np.isfinite(cube.opens[:, exit_bar, 0])
    active &= cube.opens[cube.rows, entry, selected] > 0
    active &= cube.opens[:, entry, 0] > 0
    returns = np.zeros(len(cube.sessions))
    returns[active] = (
        cube.opens[active, exit_bar, selected[active]]
        / cube.opens[active, entry, selected[active]]
        - 1.0
        - cost
    )
    benchmark = np.zeros(len(cube.sessions))
    benchmark[active] = (
        cube.opens[active, exit_bar, 0] / cube.opens[active, entry, 0] - 1.0
    )
    return v34.v12.ReturnStream(returns, benchmark, active, active.astype(int))


def _causal_parent_streams(cube, frozen_parent: dict, model):
    raw = (
        _repriced_sleeve(cube, model, v34.STANDARD_COST, 0),
        _repriced_sleeve(cube, model, v34.STRESS_COST, 0),
        _repriced_sleeve(cube, model, v34.STANDARD_COST, 1),
    )
    definition = frozen_parent["definition"]
    exposure = v42._exposure(
        raw[0].values,
        int(definition["lookback"]),
        float(definition["target_volatility"]),
        float(definition["minimum_exposure"]),
    )
    return tuple(v42._scaled(stream, exposure) for stream in raw)


def _configure() -> None:
    parent._configure()
    campaign = parent.sparse_veto.campaign
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.MECHANISM = "causal_repriced_v9292_route_plus_fixed_opening"
    campaign.base.prior.parent._parent_streams = _causal_parent_streams


if __name__ == "__main__":
    _configure()
    parent.sparse_veto.campaign.main()
