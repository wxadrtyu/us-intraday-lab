"""Development-selected causal bar-5 composites for v10605-v10704."""

from __future__ import annotations

import evaluate_full_universe_intraday_v10305_v10604_causal_gate_clock as clock


FIRST_VERSION = 10605
LAST_VERSION = 10704
PRIOR_COMPARISON_CELLS = 285_383

FACTOR_SETS = {
    "absorption_growth": (
        "relative_return", "signed_volume_imbalance", "close_location",
        "growth_minus_defensive_flow", "sector_path_efficiency_breadth",
        "vwap_distance", "growth_minus_defensive_return", "sector_flow_dispersion",
    ),
    "absorption_reclaim": (
        "relative_return", "signed_volume_imbalance", "close_location",
        "rebound_from_low", "intraday_range_position", "recent_volatility_ratio",
        "sector_breadth_acceleration", "sector_return_flow_agreement",
    ),
    "growth_reclaim": (
        "relative_return", "vwap_distance", "growth_minus_defensive_return",
        "growth_minus_defensive_flow", "rebound_from_low", "return_acceleration",
        "recent_volatility_ratio", "sector_breadth_acceleration",
    ),
    "absorption_growth_reclaim": (
        "relative_return", "signed_volume_imbalance", "close_location", "vwap_distance",
        "growth_minus_defensive_return", "growth_minus_defensive_flow", "rebound_from_low",
        "return_acceleration", "recent_volatility_ratio", "sector_breadth_acceleration",
        "sector_return_flow_agreement", "sector_path_efficiency_breadth",
    ),
    "relative_flow_growth": (
        "relative_return", "signed_volume_imbalance", "growth_minus_defensive_return",
        "growth_minus_defensive_flow", "sector_signed_flow_breadth",
    ),
    "reclaim_absorption_core": (
        "rebound_from_low", "return_acceleration", "signed_volume_imbalance",
        "close_location", "sector_return_flow_agreement",
    ),
    "growth_path_quality": (
        "relative_return", "vwap_distance", "growth_minus_defensive_return",
        "path_efficiency", "sector_path_efficiency_breadth",
    ),
    "relative_repair_quality": (
        "relative_return", "rebound_from_low", "return_acceleration",
        "path_efficiency", "sector_breadth_acceleration",
    ),
    "flow_repair_quality": (
        "signed_volume_imbalance", "growth_minus_defensive_flow", "rebound_from_low",
        "recent_volatility_ratio", "sector_return_flow_agreement",
    ),
    "balanced_top3": (
        "relative_return", "vwap_distance", "close_location", "signed_volume_imbalance",
        "growth_minus_defensive_return", "rebound_from_low", "return_acceleration",
        "recent_volatility_ratio", "sector_breadth_acceleration",
        "sector_return_flow_agreement",
    ),
}


def _configure() -> None:
    clock._configure()
    campaign = clock.parent.parent.sparse_veto.campaign
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.FACTOR_SETS = FACTOR_SETS
    campaign.MECHANISM = "causal_bar5_development_ranked_composite_gate"


if __name__ == "__main__":
    _configure()
    clock.parent.parent.sparse_veto.campaign.main()
