"""v6995-v7094: non-overlapping opening alpha plus late state route."""

from __future__ import annotations

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v4670_v5669_residual_alpha as residual
import evaluate_full_universe_intraday_v6695_v6794_state_gated_wide_fill as campaign
import evaluate_full_universe_intraday_v6895_v6994_state_interaction_fill as state_interactions
import numpy as np

FIRST_VERSION = 6995
LAST_VERSION = 7094
PRIOR_COMPARISON_CELLS = 255_855
OPENING_SLOT = (2, 17)
OPENING_FAMILY = "trend_flow_state"
OPENING_QUANTILE = 0.50
OPENING_ALPHA = 100.0


def _masked(stream, mask):
    active = stream.active & mask
    return v34.v12.ReturnStream(
        np.where(active, stream.values, 0.0),
        np.where(active, stream.benchmark, 0.0),
        active,
        np.where(active, stream.component_trades, 0),
    )


def _opening_components(
    development,
    historical,
    development_state,
    historical_state,
    core_model,
    override_model,
):
    model = residual._fit(
        development,
        OPENING_FAMILY,
        OPENING_SLOT,
        OPENING_QUANTILE,
        OPENING_ALPHA,
    )
    dev_modern, _ = campaign.prior.route._base_state(development_state, core_model, override_model)
    hist_modern, _ = campaign.prior.route._base_state(historical_state, core_model, override_model)
    scenarios = ((v34.STANDARD_COST, 0), (v34.STRESS_COST, 0), (v34.STANDARD_COST, 1))
    dev = tuple(
        _masked(residual._raw(development, model, cost, delay), dev_modern)
        for cost, delay in scenarios
    )
    hist = tuple(
        _masked(residual._raw(historical, model, cost, delay), hist_modern)
        for cost, delay in scenarios
    )
    return dev, hist


def _configure():
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.state.STATE_FAMILIES = state_interactions.STATE_FAMILIES
    campaign.EXTRA_COMPONENT_BUILDER = _opening_components
    campaign.EXTRA_COMPONENT_DEFINITION = {
        "type": "nonoverlapping_opening_alpha",
        "decision": OPENING_SLOT[0],
        "exit": OPENING_SLOT[1],
        "late_route_entry": 24,
        "factor_family": OPENING_FAMILY,
        "score_quantile": OPENING_QUANTILE,
        "ridge_alpha": OPENING_ALPHA,
        "enabled_state": "base_modern",
    }


if __name__ == "__main__":
    _configure()
    campaign.main()
