"""v11006-v11105 branch-aware causal repair of the v10824 route.

The bar-2 transfer branch may use bar-11-or-later fill because its route is
already resolved.  Modern and fallback branches use separately repriced
bar-24-or-later parents because their absence is not known until bar 23.
"""

from __future__ import annotations

import evaluate_full_universe_intraday_v9605_v9704_causal_repriced_v9292 as repriced
import evaluate_full_universe_intraday_v10805_v10904_bar5_and_boundary as boundary
import numpy as np

FIRST_VERSION = 11006
LAST_VERSION = 11105
PRIOR_COMPARISON_CELLS = 285_783
EARLY_MINIMUM_ENTRY_BAR = 11
LATE_MINIMUM_ENTRY_BAR = 24

_late_by_early: dict[int, object] = {}


def _scaled_scenarios(cube, frozen_parent, model, minimum_entry_bar):
    raw = (
        repriced._repriced_sleeve(
            cube, model, repriced.v34.STANDARD_COST, 0, minimum_entry_bar
        ),
        repriced._repriced_sleeve(
            cube, model, repriced.v34.STRESS_COST, 0, minimum_entry_bar
        ),
        repriced._repriced_sleeve(
            cube, model, repriced.v34.STANDARD_COST, 1, minimum_entry_bar
        ),
    )
    definition = frozen_parent["definition"]
    exposure = repriced.v42._exposure(
        raw[0].values,
        int(definition["lookback"]),
        float(definition["target_volatility"]),
        float(definition["minimum_exposure"]),
    )
    return tuple(repriced.v42._scaled(stream, exposure) for stream in raw)


def _branch_parent_streams(cube, frozen_parent: dict, model):
    early = _scaled_scenarios(cube, frozen_parent, model, EARLY_MINIMUM_ENTRY_BAR)
    late = _scaled_scenarios(cube, frozen_parent, model, LATE_MINIMUM_ENTRY_BAR)
    for early_stream, late_stream in zip(early, late, strict=True):
        _late_by_early[id(early_stream)] = late_stream
    return early


def _select(values_true, values_false, choose_true):
    return np.where(choose_true, values_true, values_false)


def _branch_causal_route(
    cube, cube_state, parents, core_model, override_model, gate_model, _unused
):
    opening_parent = boundary.logical.clock.parent.parent
    sparse_veto = opening_parent.sparse_veto
    campaign = sparse_veto.campaign
    route = campaign.base.prior.route
    cash = campaign.base.prior.cash
    modern_state, _ = route._base_state(cube_state, core_model, override_model)
    transfer_score = route._score(cube, gate_model)
    transfer_allowed = np.isfinite(transfer_score) & (
        transfer_score >= gate_model["threshold"]
    )
    use_transfer = (~modern_state) & transfer_allowed
    use_fallback = (~modern_state) & (~transfer_allowed)
    fallback_id = cash.FALLBACK_PARENT
    anchors = []
    for scenario in range(3):
        modern = _late_by_early[id(parents[route.MODERN_PARENT][scenario])]
        transfer = parents[route.TRANSFER_PARENT][scenario]
        fallback = _late_by_early[id(parents[fallback_id][scenario])]
        values = np.where(
            modern_state,
            modern.values,
            np.where(use_transfer, transfer.values, fallback.values),
        )
        benchmark = np.where(
            modern_state,
            modern.benchmark,
            np.where(use_transfer, transfer.benchmark, fallback.benchmark),
        )
        active = np.where(
            modern_state,
            modern.active,
            np.where(use_transfer, transfer.active, fallback.active),
        )
        trades = np.where(
            modern_state,
            modern.component_trades,
            np.where(use_transfer, transfer.component_trades, fallback.component_trades),
        )
        anchors.append(repriced.v34.v12.ReturnStream(values, benchmark, active, trades))

    early_fill = tuple(
        campaign.base.prior.wide.campaign._combine(
            [parents[item][scenario] for item in campaign.base.FILL_PARENTS],
            campaign.base.FILL_WEIGHTS,
        )
        for scenario in range(3)
    )
    late_fill = tuple(
        campaign.base.prior.wide.campaign._combine(
            [_late_by_early[id(parents[item][scenario])] for item in campaign.base.FILL_PARENTS],
            campaign.base.FILL_WEIGHTS,
        )
        for scenario in range(3)
    )
    route_resolved_early = use_transfer
    fill = tuple(
        repriced.v34.v12.ReturnStream(
            _select(early.values, late.values, route_resolved_early),
            _select(early.benchmark, late.benchmark, route_resolved_early),
            _select(early.active, late.active, route_resolved_early).astype(bool),
            _select(early.component_trades, late.component_trades, route_resolved_early),
        )
        for early, late in zip(early_fill, late_fill, strict=True)
    )
    if sparse_veto._fill_model is None:
        sparse_veto._fill_model = campaign.base.state._fit_state(
            cube_state,
            campaign.base.state.STATE_FAMILIES[sparse_veto.FROZEN_STATE_FAMILY],
            sparse_veto.FROZEN_STATE_QUANTILE,
        )
    allowed = campaign.base._allowed(
        cube_state, sparse_veto._fill_model, sparse_veto.FROZEN_ORIENTATION
    )
    late_route = tuple(
        campaign.base._disjoint_gated(anchor, extra, allowed)
        for anchor, extra in zip(anchors, fill, strict=True)
    )
    if sparse_veto._opening_model is None:
        sparse_veto._opening_model = opening_parent.residual._fit(
            cube,
            opening_parent.sparse_gap.OPENING_FAMILY,
            opening_parent.sparse_gap.OPENING_SLOT,
            opening_parent.sparse_gap.OPENING_QUANTILE,
            opening_parent.sparse_gap.OPENING_ALPHA,
        )
    scenarios = (
        (campaign.v34.STANDARD_COST, 0),
        (campaign.v34.STRESS_COST, 0),
        (campaign.v34.STANDARD_COST, 1),
    )
    opening = tuple(
        opening_parent.sparse_gap.campaign._masked(
            opening_parent.residual._raw(
                cube, sparse_veto._opening_model, cost, delay
            ),
            modern_state,
        )
        for cost, delay in scenarios
    )
    for late_stream, opening_stream in zip(late_route, opening, strict=True):
        opening_parent._opening_by_late_stream[id(late_stream)] = opening_stream
    return late_route


def _configure() -> None:
    _late_by_early.clear()
    boundary._configure()
    campaign = boundary.logical.clock.parent.parent.sparse_veto.campaign
    campaign.base.prior.parent._parent_streams = _branch_parent_streams
    campaign._route = _branch_causal_route
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.MECHANISM = "branch_resolved_early_transfer_late_modern_fill"


if __name__ == "__main__":
    _configure()
    boundary.logical.clock.parent.parent.sparse_veto.campaign.main()
