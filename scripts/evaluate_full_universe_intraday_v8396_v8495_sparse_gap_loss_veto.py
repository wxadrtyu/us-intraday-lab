"""v8396-v8495: causal loss veto over the frozen sparse-gap route."""

from __future__ import annotations

import evaluate_full_universe_intraday_v4670_v5669_residual_alpha as residual
import evaluate_full_universe_intraday_v7395_v7494_full_route_loss_veto as campaign
import evaluate_full_universe_intraday_v7495_v7594_last_bar_loss_veto as last_bar
import evaluate_full_universe_intraday_v7996_v8095_sparse_opening_gap as sparse_gap

FIRST_VERSION = 8396
LAST_VERSION = 8495
PRIOR_COMPARISON_CELLS = 257_266
GATE_DECISION = 23
ENTRY_BAR = 24
FROZEN_ROUTE_VERSION = 8055
FROZEN_STATE_FAMILY = "volatile_breadth_repair"
FROZEN_STATE_QUANTILE = 0.80
FROZEN_ORIENTATION = "fill_on_low"

_fill_model = None
_opening_model = None


def _sparse_gap_route(cube, cube_state, parents, core_model, override_model, gate_model, _unused):
    global _fill_model, _opening_model
    base_ids = tuple(
        dict.fromkeys(
            (
                campaign.base.prior.route.MODERN_PARENT,
                campaign.base.prior.route.TRANSFER_PARENT,
                campaign.base.prior.cash.FALLBACK_PARENT,
            )
        )
    )
    anchors = campaign.base.prior._base_streams(
        cube,
        cube_state,
        {item: parents[item] for item in base_ids},
        core_model,
        override_model,
        gate_model,
    )
    fill = tuple(
        campaign.base.prior.wide.campaign._combine(
            [parents[item][scenario] for item in campaign.base.FILL_PARENTS],
            campaign.base.FILL_WEIGHTS,
        )
        for scenario in range(3)
    )
    if _fill_model is None:
        _fill_model = campaign.base.state._fit_state(
            cube_state,
            campaign.base.state.STATE_FAMILIES[FROZEN_STATE_FAMILY],
            FROZEN_STATE_QUANTILE,
        )
    allowed = campaign.base._allowed(cube_state, _fill_model, FROZEN_ORIENTATION)
    late = tuple(
        campaign.base._disjoint_gated(anchor, extra, allowed)
        for anchor, extra in zip(anchors, fill, strict=True)
    )
    if _opening_model is None:
        _opening_model = residual._fit(
            cube,
            sparse_gap.OPENING_FAMILY,
            sparse_gap.OPENING_SLOT,
            sparse_gap.OPENING_QUANTILE,
            sparse_gap.OPENING_ALPHA,
        )
    modern, _ = campaign.base.prior.route._base_state(cube_state, core_model, override_model)
    scenarios = (
        (campaign.v34.STANDARD_COST, 0),
        (campaign.v34.STRESS_COST, 0),
        (campaign.v34.STANDARD_COST, 1),
    )
    opening = tuple(
        sparse_gap.campaign._masked(residual._raw(cube, _opening_model, cost, delay), modern)
        for cost, delay in scenarios
    )
    return campaign.base._combine_extra(late, opening)


def _configure():
    global _fill_model, _opening_model
    _fill_model = None
    _opening_model = None
    sparse_gap._configure()
    last_bar._configure()
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.GATE_DECISION = GATE_DECISION
    campaign.ENTRY_BAR = ENTRY_BAR
    campaign.quality.GATE_DECISION = GATE_DECISION
    campaign._route = _sparse_gap_route


if __name__ == "__main__":
    _configure()
    campaign.main()
