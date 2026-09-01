"""v9104-v9203 causal late-route soft veto without retrospective opening exposure."""

from __future__ import annotations

import evaluate_full_universe_intraday_v8396_v8495_sparse_gap_loss_veto as sparse_veto
import numpy as np

FIRST_VERSION = 9104
LAST_VERSION = 9203
PRIOR_COMPARISON_CELLS = 257_982
QUANTILES = (0.10, 0.15, 0.20, 0.25, 0.30)
ALPHAS = (30.0, 100.0)
LOW_EXPOSURE = 0.25
GATE_DECISION = 23
ENTRY_BAR = 24


def _late_only_route(cube, cube_state, parents, core_model, override_model, gate_model, _unused):
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
    return tuple(
        campaign.base._disjoint_gated(anchor, extra, allowed)
        for anchor, extra in zip(anchors, fill, strict=True)
    )


def _soft_veto(stream, allowed):
    exposure = np.where(allowed, 1.0, LOW_EXPOSURE)
    return sparse_veto.campaign.v34.v12.ReturnStream(
        stream.values * exposure,
        stream.benchmark * exposure,
        stream.active,
        stream.component_trades,
    )


def _configure() -> None:
    sparse_veto._configure()
    campaign = sparse_veto.campaign
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.GATE_DECISION = GATE_DECISION
    campaign.ENTRY_BAR = ENTRY_BAR
    campaign.quality.GATE_DECISION = GATE_DECISION
    campaign.QUANTILES = QUANTILES
    campaign.ALPHAS = ALPHAS
    campaign._route = _late_only_route
    campaign.STREAM_TRANSFORM = _soft_veto
    campaign.MECHANISM = "causal_late_route_soft_25pct_veto"


if __name__ == "__main__":
    _configure()
    sparse_veto.campaign.main()
