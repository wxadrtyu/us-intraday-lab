"""v9204-v9303 causal fixed opening plus bar-23-gated late route."""

from __future__ import annotations

import evaluate_full_universe_intraday_v4670_v5669_residual_alpha as residual
import evaluate_full_universe_intraday_v7996_v8095_sparse_opening_gap as sparse_gap
import evaluate_full_universe_intraday_v8396_v8495_sparse_gap_loss_veto as sparse_veto
import numpy as np

FIRST_VERSION = 9204
LAST_VERSION = 9303
PRIOR_COMPARISON_CELLS = 258_082
QUANTILES = (0.10, 0.15, 0.20, 0.25, 0.30)
ALPHAS = (30.0, 100.0)
LOW_EXPOSURE = 0.25
OPENING_DECISION = 2
OPENING_ENTRY = 3
OPENING_EXIT = 11
LATE_GATE_DECISION = 23
LATE_ENTRY = 24

_opening_by_late_stream: dict[int, object] = {}


def _causal_route(cube, cube_state, parents, core_model, override_model, gate_model, _unused):
    campaign = sparse_veto.campaign
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
    if sparse_veto._fill_model is None:
        sparse_veto._fill_model = campaign.base.state._fit_state(
            cube_state,
            campaign.base.state.STATE_FAMILIES[sparse_veto.FROZEN_STATE_FAMILY],
            sparse_veto.FROZEN_STATE_QUANTILE,
        )
    allowed = campaign.base._allowed(
        cube_state, sparse_veto._fill_model, sparse_veto.FROZEN_ORIENTATION
    )
    late = tuple(
        campaign.base._disjoint_gated(anchor, extra, allowed)
        for anchor, extra in zip(anchors, fill, strict=True)
    )
    if sparse_veto._opening_model is None:
        sparse_veto._opening_model = residual._fit(
            cube,
            sparse_gap.OPENING_FAMILY,
            sparse_gap.OPENING_SLOT,
            sparse_gap.OPENING_QUANTILE,
            sparse_gap.OPENING_ALPHA,
        )
    modern, _ = campaign.base.prior.route._base_state(
        cube_state, core_model, override_model
    )
    scenarios = (
        (campaign.v34.STANDARD_COST, 0),
        (campaign.v34.STRESS_COST, 0),
        (campaign.v34.STANDARD_COST, 1),
    )
    opening = tuple(
        sparse_gap.campaign._masked(
            residual._raw(cube, sparse_veto._opening_model, cost, delay), modern
        )
        for cost, delay in scenarios
    )
    for late_stream, opening_stream in zip(late, opening, strict=True):
        _opening_by_late_stream[id(late_stream)] = opening_stream
    return late


def _late_soft_veto_plus_fixed_opening(stream, allowed):
    opening = _opening_by_late_stream.get(id(stream))
    if opening is None:
        raise RuntimeError("CAUSAL_OPENING_STREAM_NOT_REGISTERED")
    exposure = np.where(allowed, 1.0, LOW_EXPOSURE)
    return sparse_veto.campaign.v34.v12.ReturnStream(
        stream.values * exposure + opening.values,
        stream.benchmark * exposure + opening.benchmark,
        stream.active | opening.active,
        stream.component_trades + opening.component_trades,
    )


def _configure() -> None:
    _opening_by_late_stream.clear()
    sparse_veto._configure()
    campaign = sparse_veto.campaign
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.GATE_DECISION = LATE_GATE_DECISION
    campaign.ENTRY_BAR = LATE_ENTRY
    campaign.quality.GATE_DECISION = LATE_GATE_DECISION
    campaign.QUANTILES = QUANTILES
    campaign.ALPHAS = ALPHAS
    campaign._route = _causal_route
    campaign.STREAM_TRANSFORM = _late_soft_veto_plus_fixed_opening
    campaign.MECHANISM = "causal_fixed_opening_plus_late_soft_25pct_veto"


if __name__ == "__main__":
    _configure()
    sparse_veto.campaign.main()
