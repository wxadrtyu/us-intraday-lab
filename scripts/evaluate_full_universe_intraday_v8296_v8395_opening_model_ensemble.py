"""v8296-v8395: opening-model ensemble, pre-route sleeve, and late route."""

from __future__ import annotations

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v4670_v5669_residual_alpha as residual
import evaluate_full_universe_intraday_v8196_v8295_dual_intraday_sleeve as dual

FIRST_VERSION = 8296
LAST_VERSION = 8395
PRIOR_COMPARISON_CELLS = 257_166
AUCTION_FAMILY = "ensemble_opening_auction_absorption"
AUCTION_FACTORS = (
    "signed_volume_imbalance",
    "volume_acceleration",
    "trend_consistency",
    "vwap_distance",
    "close_location",
    "range_ratio",
    "relative_return",
    "sector_breadth",
)


def _average_concurrent(left, right):
    return v34.v12.ReturnStream(
        0.5 * (left.values + right.values),
        0.5 * (left.benchmark + right.benchmark),
        left.active | right.active,
        left.component_trades + right.component_trades,
    )


def _ensemble_components(
    development,
    historical,
    development_state,
    historical_state,
    core_model,
    override_model,
):
    gap_model = residual._fit(
        development,
        dual.OPENING_FAMILY,
        dual.OPENING_SLOT,
        dual.SCORE_QUANTILE,
        dual.RIDGE_ALPHA,
    )
    auction_model = residual._fit(
        development,
        AUCTION_FAMILY,
        dual.OPENING_SLOT,
        dual.SCORE_QUANTILE,
        dual.RIDGE_ALPHA,
    )
    preroute_model = residual._fit(
        development,
        dual.PREROUTE_FAMILY,
        dual.PREROUTE_SLOT,
        dual.SCORE_QUANTILE,
        dual.RIDGE_ALPHA,
    )
    dev_modern, _ = dual.foundation.campaign.prior.route._base_state(
        development_state, core_model, override_model
    )
    hist_modern, _ = dual.foundation.campaign.prior.route._base_state(
        historical_state, core_model, override_model
    )
    scenarios = ((v34.STANDARD_COST, 0), (v34.STRESS_COST, 0), (v34.STANDARD_COST, 1))

    def build(cube, modern):
        output = []
        for cost, delay in scenarios:
            gap = dual.foundation._masked(residual._raw(cube, gap_model, cost, delay), modern)
            auction = dual.foundation._masked(
                residual._raw(cube, auction_model, cost, delay), modern
            )
            preroute = dual.foundation._masked(
                residual._raw(cube, preroute_model, cost, delay), modern
            )
            output.append(dual._combine_sequential(_average_concurrent(gap, auction), preroute))
        return tuple(output)

    return build(development, dev_modern), build(historical, hist_modern)


def _configure():
    dual._configure()
    residual.FACTOR_SETS[AUCTION_FAMILY] = AUCTION_FACTORS
    dual.foundation.campaign.FIRST_VERSION = FIRST_VERSION
    dual.foundation.campaign.LAST_VERSION = LAST_VERSION
    dual.foundation.campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    dual.foundation.campaign.EXTRA_COMPONENT_BUILDER = _ensemble_components
    dual.foundation.campaign.EXTRA_COMPONENT_DEFINITION = {
        "type": "opening_two_model_equal_gross_then_preroute_residual",
        "opening_models": [dual.OPENING_FAMILY, AUCTION_FAMILY],
        "opening_model_weights": [0.5, 0.5],
        "opening": {"decision": 2, "entry": 3, "exit": 11},
        "preroute": {
            "decision": 11,
            "entry": 12,
            "exit": 23,
            "factor_family": dual.PREROUTE_FAMILY,
        },
        "late_route_entry": 24,
        "score_quantile": dual.SCORE_QUANTILE,
        "ridge_alpha": dual.RIDGE_ALPHA,
        "enabled_state": "base_modern",
    }


if __name__ == "__main__":
    _configure()
    dual.foundation.campaign.main()
