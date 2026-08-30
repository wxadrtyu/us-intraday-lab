"""v8196-v8295: two time-disjoint intraday residual sleeves plus late route."""

from __future__ import annotations

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v4670_v5669_residual_alpha as residual
import evaluate_full_universe_intraday_v6995_v7094_opening_late_ensemble as foundation

FIRST_VERSION = 8196
LAST_VERSION = 8295
PRIOR_COMPARISON_CELLS = 257_066
OPENING_SLOT = (2, 11)
PREROUTE_SLOT = (11, 23)
SCORE_QUANTILE = 0.80
RIDGE_ALPHA = 1000.0
OPENING_FAMILY = "dual_sparse_opening_gap"
PREROUTE_FAMILY = "dual_sparse_liquidity_absorption"
OPENING_FACTORS = (
    "gap",
    "current_return",
    "relative_return",
    "vwap_distance",
    "close_location",
    "path_efficiency",
    "signed_volume_imbalance",
    "spy_prior20",
)
PREROUTE_FACTORS = (
    "signed_volume_imbalance",
    "volume_acceleration",
    "vwap_distance",
    "close_location",
    "range_ratio",
    "realized_volatility",
    "relative_return",
    "sector_breadth",
)


def _combine_sequential(left, right):
    return v34.v12.ReturnStream(
        left.values + right.values,
        left.benchmark + right.benchmark,
        left.active | right.active,
        left.component_trades + right.component_trades,
    )


def _dual_components(
    development,
    historical,
    development_state,
    historical_state,
    core_model,
    override_model,
):
    opening_model = residual._fit(
        development, OPENING_FAMILY, OPENING_SLOT, SCORE_QUANTILE, RIDGE_ALPHA
    )
    preroute_model = residual._fit(
        development, PREROUTE_FAMILY, PREROUTE_SLOT, SCORE_QUANTILE, RIDGE_ALPHA
    )
    dev_modern, _ = foundation.campaign.prior.route._base_state(
        development_state, core_model, override_model
    )
    hist_modern, _ = foundation.campaign.prior.route._base_state(
        historical_state, core_model, override_model
    )
    scenarios = ((v34.STANDARD_COST, 0), (v34.STRESS_COST, 0), (v34.STANDARD_COST, 1))

    def build(cube, modern):
        return tuple(
            _combine_sequential(
                foundation._masked(residual._raw(cube, opening_model, cost, delay), modern),
                foundation._masked(residual._raw(cube, preroute_model, cost, delay), modern),
            )
            for cost, delay in scenarios
        )

    return build(development, dev_modern), build(historical, hist_modern)


def _configure():
    residual.FACTOR_SETS[OPENING_FAMILY] = OPENING_FACTORS
    residual.FACTOR_SETS[PREROUTE_FAMILY] = PREROUTE_FACTORS
    foundation._configure()
    foundation.campaign.FIRST_VERSION = FIRST_VERSION
    foundation.campaign.LAST_VERSION = LAST_VERSION
    foundation.campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    foundation.campaign.EXTRA_COMPONENT_BUILDER = _dual_components
    foundation.campaign.EXTRA_COMPONENT_DEFINITION = {
        "type": "two_nonoverlapping_sparse_intraday_residual_sleeves",
        "opening": {"decision": 2, "entry": 3, "exit": 11, "factor_family": OPENING_FAMILY},
        "preroute": {
            "decision": 11,
            "entry": 12,
            "exit": 23,
            "factor_family": PREROUTE_FAMILY,
        },
        "late_route_entry": 24,
        "score_quantile": SCORE_QUANTILE,
        "ridge_alpha": RIDGE_ALPHA,
        "enabled_state": "base_modern",
    }


if __name__ == "__main__":
    _configure()
    foundation.campaign.main()
