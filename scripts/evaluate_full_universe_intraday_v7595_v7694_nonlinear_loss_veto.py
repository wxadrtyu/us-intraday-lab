"""v7595-v7694 nonlinear path-times-sector loss veto."""

from __future__ import annotations

import evaluate_full_universe_intraday_v5670_v5769_modern_quality_gate as quality
import evaluate_full_universe_intraday_v5970_v6069_sector_flow_leadership as sector
import evaluate_full_universe_intraday_v7395_v7494_full_route_loss_veto as campaign

FIRST_VERSION = 7595
LAST_VERSION = 7694
PRIOR_COMPARISON_CELLS = 256_455
GATE_DECISION = 17
ENTRY_BAR = 24


class NonlinearInteractionCube(sector.SectorFlowLeadershipCube):
    def factors(self, decision: int):
        output = super().factors(decision)
        if "drawdown_x_flow" in output:
            return output
        interactions = {
            "drawdown_x_flow": ("drawdown_from_high", "sector_signed_flow_breadth"),
            "rebound_x_breadth_accel": ("rebound_from_low", "sector_breadth_acceleration"),
            "return_accel_x_agreement": ("return_acceleration", "sector_return_flow_agreement"),
            "relative_x_growth_flow": ("relative_return", "growth_minus_defensive_flow"),
            "vol_ratio_x_sector_contraction": ("recent_volatility_ratio", "sector_volatility_contraction"),
            "imbalance_x_flow_breadth": ("signed_volume_imbalance", "sector_signed_flow_breadth"),
            "close_location_x_path_breadth": ("close_location", "sector_path_efficiency_breadth"),
            "vwap_x_flow_dispersion": ("vwap_distance", "sector_flow_dispersion"),
            "path_efficiency_x_agreement": ("path_efficiency", "sector_return_flow_agreement"),
            "volume_accel_x_breadth_accel": ("volume_acceleration", "sector_breadth_acceleration"),
        }
        for name, (left, right) in interactions.items():
            output[name] = output[left] * output[right]
        return output


FACTOR_SETS = {
    "nonlinear_absorption": ("drawdown_x_flow", "rebound_x_breadth_accel", "return_accel_x_agreement"),
    "nonlinear_relative_flow": ("relative_x_growth_flow", "imbalance_x_flow_breadth", "vwap_x_flow_dispersion"),
    "nonlinear_contraction": ("vol_ratio_x_sector_contraction", "return_accel_x_agreement", "volume_accel_x_breadth_accel"),
    "nonlinear_path_quality": ("close_location_x_path_breadth", "path_efficiency_x_agreement", "rebound_x_breadth_accel"),
    "absorption_plus_levels": ("drawdown_x_flow", "return_acceleration", "sector_signed_flow_breadth", "sector_return_flow_agreement"),
    "relative_plus_levels": ("relative_x_growth_flow", "relative_return", "growth_minus_defensive_flow", "sector_flow_dispersion"),
    "contraction_plus_levels": ("vol_ratio_x_sector_contraction", "recent_volatility_ratio", "sector_volatility_contraction", "sector_breadth_acceleration"),
    "flow_plus_levels": ("imbalance_x_flow_breadth", "signed_volume_imbalance", "sector_signed_flow_breadth", "sector_return_flow_agreement"),
    "path_plus_levels": ("path_efficiency_x_agreement", "path_efficiency", "close_location", "sector_path_efficiency_breadth"),
    "balanced_nonlinear": ("drawdown_x_flow", "rebound_x_breadth_accel", "return_accel_x_agreement", "relative_x_growth_flow", "vol_ratio_x_sector_contraction", "imbalance_x_flow_breadth", "close_location_x_path_breadth", "vwap_x_flow_dispersion", "path_efficiency_x_agreement", "volume_accel_x_breadth_accel"),
}


def _configure() -> None:
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.GATE_DECISION = GATE_DECISION
    campaign.ENTRY_BAR = ENTRY_BAR
    campaign.FACTOR_SETS = FACTOR_SETS
    quality.GATE_DECISION = GATE_DECISION
    sector.SectorFlowLeadershipCube = NonlinearInteractionCube


if __name__ == "__main__":
    _configure()
    campaign.main()
