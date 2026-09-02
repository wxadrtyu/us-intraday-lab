"""v9705-v9804 causal composite gates over the repriced v9292 successor."""

from __future__ import annotations

import evaluate_full_universe_intraday_v9605_v9704_causal_repriced_v9292 as parent


FIRST_VERSION = 9705
LAST_VERSION = 9804
PRIOR_COMPARISON_CELLS = 284_483

FACTOR_SETS = {
    "growth_volatility": (
        "relative_return", "vwap_distance", "growth_minus_defensive_return",
        "realized_volatility", "recent_volatility_ratio",
    ),
    "growth_liquidity": (
        "relative_return", "growth_minus_defensive_return", "growth_minus_defensive_flow",
        "recent_volume_ratio", "sector_flow_dispersion",
    ),
    "growth_absorption": (
        "relative_return", "vwap_distance", "close_location",
        "signed_volume_imbalance", "sector_return_flow_agreement",
    ),
    "growth_repair": (
        "growth_minus_defensive_return", "growth_minus_defensive_flow", "rebound_from_low",
        "return_acceleration", "sector_breadth_acceleration",
    ),
    "growth_leadership": (
        "relative_return", "current_rank", "growth_minus_defensive_return",
        "sector_leadership_spread", "sector_leadership_concentration",
    ),
    "prior_growth_volatility": (
        "prior1_return", "prior20_return", "growth_minus_defensive_return",
        "realized_volatility", "recent_volatility_ratio",
    ),
    "liquid_reclaim": (
        "rebound_from_low", "intraday_range_position", "recent_volume_ratio",
        "recent_volatility_ratio", "sector_volatility_contraction",
    ),
    "flow_volatility": (
        "signed_volume_imbalance", "volume_acceleration", "recent_volume_ratio",
        "realized_volatility", "sector_signed_flow_breadth",
    ),
    "risk_quality": (
        "drawdown_from_high", "path_efficiency", "recent_volatility_ratio",
        "sector_path_efficiency_breadth", "sector_volatility_contraction",
    ),
    "balanced_growth_quality": (
        "relative_return", "vwap_distance", "growth_minus_defensive_return",
        "growth_minus_defensive_flow", "realized_volatility", "recent_volume_ratio",
        "sector_breadth_acceleration", "sector_return_flow_agreement",
    ),
}


def _configure() -> None:
    parent._configure()
    campaign = parent.parent.sparse_veto.campaign
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.FACTOR_SETS = FACTOR_SETS
    campaign.MECHANISM = "causal_repriced_v9292_composite_quality_gate"


if __name__ == "__main__":
    _configure()
    parent.parent.sparse_veto.campaign.main()
