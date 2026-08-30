"""v7095-v7194: prior-close regime gate over the opening alpha component."""

from __future__ import annotations

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v4670_v5669_residual_alpha as residual
import evaluate_full_universe_intraday_v6995_v7094_opening_late_ensemble as base
import numpy as np

FIRST_VERSION = 7095
LAST_VERSION = 7194
PRIOR_COMPARISON_CELLS = 255_955
OPENING_STATE_FAMILY = "low_dispersion_trend"
OPENING_STATE_QUANTILE = 0.50


def _allowed_state(cube, model):
    score = base.campaign.state._score(cube, model)
    return np.isfinite(score) & (score >= model["threshold"])


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
        base.OPENING_FAMILY,
        base.OPENING_SLOT,
        base.OPENING_QUANTILE,
        base.OPENING_ALPHA,
    )
    dev_modern, _ = base.campaign.prior.route._base_state(
        development_state, core_model, override_model
    )
    hist_modern, _ = base.campaign.prior.route._base_state(
        historical_state, core_model, override_model
    )
    opening_state_model = base.campaign.state._fit_state(
        development_state,
        base.campaign.CORE_LOW_DISPERSION_TREND,
        OPENING_STATE_QUANTILE,
    )
    dev_mask = dev_modern & _allowed_state(development_state, opening_state_model)
    hist_mask = hist_modern & _allowed_state(historical_state, opening_state_model)
    scenarios = ((v34.STANDARD_COST, 0), (v34.STRESS_COST, 0), (v34.STANDARD_COST, 1))
    dev = tuple(
        base._masked(residual._raw(development, model, cost, delay), dev_mask)
        for cost, delay in scenarios
    )
    hist = tuple(
        base._masked(residual._raw(historical, model, cost, delay), hist_mask)
        for cost, delay in scenarios
    )
    return dev, hist


def _configure():
    base._configure()
    campaign = base.campaign
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.EXTRA_COMPONENT_BUILDER = _opening_components
    campaign.EXTRA_COMPONENT_DEFINITION = {
        "type": "prior_close_regime_gated_opening_alpha",
        "decision": base.OPENING_SLOT[0],
        "exit": base.OPENING_SLOT[1],
        "late_route_entry": 24,
        "factor_family": base.OPENING_FAMILY,
        "score_quantile": base.OPENING_QUANTILE,
        "ridge_alpha": base.OPENING_ALPHA,
        "enabled_base_state": "base_modern",
        "prior_close_state_family": OPENING_STATE_FAMILY,
        "prior_close_state_quantile": OPENING_STATE_QUANTILE,
        "prior_close_state_orientation": "high",
    }


if __name__ == "__main__":
    _configure()
    base.campaign.main()
