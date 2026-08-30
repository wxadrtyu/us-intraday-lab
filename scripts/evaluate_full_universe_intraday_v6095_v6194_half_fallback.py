"""v6095-v6194: retain half risk when the early modern gate rejects."""

from __future__ import annotations

import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v5670_v5769_modern_quality_gate as linear_gate
import evaluate_full_universe_intraday_v5870_v5969_nonlinear_meta_gate as campaign
import numpy as np

FALLBACK_EXPOSURE = 0.50
FIRST_VERSION = 6095
LAST_VERSION = 6194
PRIOR_COMPARISON_CELLS = 254_955
GATE_DECISION = 2
FACTOR_SETS = {
    "early_trend_flow": (
        "current_return",
        "relative_return",
        "path_efficiency",
        "signed_volume_imbalance",
    ),
    "early_structure": ("current_return", "vwap_distance", "close_location", "session_range"),
    "early_cross_state": ("relative_return", "current_rank", "prior20_rank", "sector_breadth"),
    "early_reclaim": ("recent_return", "drawdown_from_high", "rebound_from_low", "close_location"),
    "early_balanced": (
        "current_return",
        "relative_return",
        "path_efficiency",
        "signed_volume_imbalance",
        "vwap_distance",
        "close_location",
        "prior20_return",
        "spy_volatility",
    ),
}


def _half_fallback_route(parents, base_modern, allow_modern, allow_transfer):
    """Use full modern risk on acceptance and half risk on rejection."""
    accepted = base_modern & allow_modern
    rejected = base_modern & ~allow_modern
    transfer_mask = (~base_modern) & allow_transfer
    output = []
    for modern, transfer in zip(
        parents[linear_gate.MODERN_PARENT],
        parents[linear_gate.TRANSFER_PARENT],
        strict=True,
    ):
        modern_scale = np.where(accepted, 1.0, np.where(rejected, FALLBACK_EXPOSURE, 0.0))
        values = np.where(
            base_modern, modern.values * modern_scale, np.where(transfer_mask, transfer.values, 0.0)
        )
        benchmark = np.where(
            base_modern,
            modern.benchmark * modern_scale,
            np.where(transfer_mask, transfer.benchmark, 0.0),
        )
        active = np.where(base_modern, modern.active, transfer_mask & transfer.active)
        trades = np.where(
            base_modern,
            modern.component_trades,
            np.where(transfer_mask, transfer.component_trades, 0),
        )
        output.append(v34.v12.ReturnStream(values, benchmark, active, trades))
    return tuple(output)


def _configure():
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.GATE_DECISION = GATE_DECISION
    campaign.MECHANISM = "v4513_nonlinear_early_state_half_risk_fallback"
    campaign.FACTOR_SETS = FACTOR_SETS
    linear_gate._route = _half_fallback_route


if __name__ == "__main__":
    _configure()
    campaign.main()
