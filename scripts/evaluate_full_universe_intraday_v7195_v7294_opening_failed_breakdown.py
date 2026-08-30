"""v7195-v7294: oversold-state opening reclaim plus late route."""

from __future__ import annotations

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v4670_v5669_residual_alpha as residual
import evaluate_full_universe_intraday_v6995_v7094_opening_late_ensemble as base
import numpy as np

FIRST_VERSION = 7195
LAST_VERSION = 7294
PRIOR_COMPARISON_CELLS = 256_055
OPENING_SLOT = (8, 23)
OPENING_FAMILY = "opening_reclaim"
OPENING_FACTORS = (
    "current_return",
    "recent_return",
    "vwap_distance",
    "close_location",
    "signed_volume_imbalance",
    "volume_acceleration",
    "prior1_return",
    "spy_prior20",
)
OPENING_QUANTILE = 0.70
OPENING_ALPHA = 100.0
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
    residual.FACTOR_SETS[OPENING_FAMILY] = OPENING_FACTORS
    model = residual._fit(
        development,
        OPENING_FAMILY,
        OPENING_SLOT,
        OPENING_QUANTILE,
        OPENING_ALPHA,
    )
    dev_modern, _ = base.campaign.prior.route._base_state(
        development_state, core_model, override_model
    )
    hist_modern, _ = base.campaign.prior.route._base_state(
        historical_state, core_model, override_model
    )
    opening_state_model = base.campaign.state._fit_state(
        development_state,
        base.campaign.CORE_OVERSOLD_REPAIR,
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
        "type": "oversold_state_opening_reclaim",
        "decision": OPENING_SLOT[0],
        "exit": OPENING_SLOT[1],
        "late_route_entry": 24,
        "factor_family": OPENING_FAMILY,
        "factors": OPENING_FACTORS,
        "score_quantile": OPENING_QUANTILE,
        "ridge_alpha": OPENING_ALPHA,
        "enabled_base_state": "base_modern",
        "prior_close_state_family": "oversold_repair",
        "prior_close_state_quantile": OPENING_STATE_QUANTILE,
        "prior_close_state_orientation": "high",
    }


if __name__ == "__main__":
    _configure()
    base.campaign.main()
