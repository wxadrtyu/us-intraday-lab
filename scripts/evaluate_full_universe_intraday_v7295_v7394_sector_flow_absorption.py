"""v7295-v7394 preregistered sector-flow absorption quality gate."""

from __future__ import annotations

import evaluate_full_universe_intraday_v5670_v5769_modern_quality_gate as campaign
from evaluate_full_universe_intraday_v5970_v6069_sector_flow_leadership import (
    SectorFlowLeadershipCube,
)

FIRST_VERSION = 7295
LAST_VERSION = 7394
PRIOR_COMPARISON_CELLS = 256_155
GATE_DECISION = 17
MODERN_ENTRY = 24
QUANTILES = (0.0, 0.2, 0.4, 0.6, 0.8)
ALPHAS = (1.0, 100.0)

FACTOR_SETS = {
    "flow_absorbed_breakdown": (
        "drawdown_from_high",
        "rebound_from_low",
        "return_acceleration",
        "sector_signed_flow_breadth",
        "sector_return_flow_agreement",
    ),
    "quiet_flow_reclaim": (
        "recent_volatility_ratio",
        "intraday_range_position",
        "signed_volume_imbalance",
        "sector_volatility_contraction",
        "sector_breadth_acceleration",
    ),
    "relative_laggard_absorption": (
        "relative_return",
        "drawdown_from_high",
        "recent_volume_ratio",
        "sector_flow_dispersion",
        "growth_minus_defensive_flow",
    ),
    "broad_recovery_confirmation": (
        "rebound_from_low",
        "return_acceleration",
        "close_location",
        "sector_breadth_acceleration",
        "sector_path_efficiency_breadth",
    ),
    "failed_breakdown_leadership": (
        "drawdown_from_high",
        "intraday_range_position",
        "signed_volume_imbalance",
        "sector_leadership_spread",
        "sector_leadership_concentration",
    ),
    "growth_flow_repair": (
        "relative_return",
        "rebound_from_low",
        "vwap_distance",
        "growth_minus_defensive_return",
        "growth_minus_defensive_flow",
    ),
    "contraction_absorption_release": (
        "recent_volatility_ratio",
        "recent_volume_ratio",
        "return_acceleration",
        "sector_volatility_contraction",
        "sector_signed_flow_breadth",
    ),
    "efficient_flow_reclaim": (
        "path_efficiency",
        "close_location",
        "rebound_from_low",
        "sector_path_efficiency_breadth",
        "sector_return_flow_agreement",
    ),
    "dispersion_reversal": (
        "drawdown_from_high",
        "return_acceleration",
        "relative_return",
        "sector_flow_dispersion",
        "sector_leadership_spread",
        "sector_breadth_acceleration",
    ),
    "balanced_absorption": (
        "drawdown_from_high",
        "rebound_from_low",
        "return_acceleration",
        "signed_volume_imbalance",
        "recent_volatility_ratio",
        "sector_signed_flow_breadth",
        "sector_return_flow_agreement",
        "sector_breadth_acceleration",
        "sector_volatility_contraction",
        "growth_minus_defensive_flow",
    ),
}


def specifications():
    return [
        (family, quantile, alpha)
        for family in FACTOR_SETS
        for quantile in QUANTILES
        for alpha in ALPHAS
    ]


def main() -> None:
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.GATE_DECISION = GATE_DECISION
    campaign.MODERN_ENTRY = MODERN_ENTRY
    campaign.QUANTILES = QUANTILES
    campaign.ALPHAS = ALPHAS
    campaign.FACTOR_SETS = FACTOR_SETS
    campaign.IntradayPathCube = SectorFlowLeadershipCube
    campaign.main()


if __name__ == "__main__":
    main()
