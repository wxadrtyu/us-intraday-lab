"""v6195-v6294: downside-sensitive early-state quality with half fallback."""

from __future__ import annotations

import evaluate_full_universe_intraday_v30_extra_trees as trees
import evaluate_full_universe_intraday_v34_multifactor as v34
import evaluate_full_universe_intraday_v5670_v5769_modern_quality_gate as linear_gate
import evaluate_full_universe_intraday_v5870_v5969_nonlinear_meta_gate as campaign
import numpy as np

FALLBACK_EXPOSURE = 0.50
DOWNSIDE_PENALTY = 2.0


def _downside_target(excess_return):
    """Penalize negative training outcomes without using diagnostic periods."""
    values = np.asarray(excess_return, dtype=float)
    return np.where(values < 0.0, values * DOWNSIDE_PENALTY, values)


def _fit(cube, modern, base_modern, factors, depth, min_leaf, quantile, seed):
    matrix = campaign._matrix(cube, factors)
    train = cube.masks()["train_2022_2023"] & base_modern & modern.active
    medians = np.nanmedian(matrix[train], axis=0)
    values = np.where(np.isfinite(matrix), matrix, medians)
    target = _downside_target(modern.values - modern.benchmark)
    selected = values[train]
    labels = target[train]
    generator = np.random.default_rng(seed)
    forest = []
    for _ in range(64):
        sample = generator.integers(0, len(labels), size=len(labels))
        forest.append(trees._fit_node(selected[sample], labels[sample], depth, min_leaf, generator))
    prediction = trees._predict(forest, values)
    threshold = float(np.quantile(prediction[train], quantile))
    return {"factors": factors, "medians": medians, "trees": forest, "threshold": threshold}


def _route(parents, base_modern, allow_modern, allow_transfer):
    accepted = base_modern & allow_modern
    rejected = base_modern & ~allow_modern
    transfer_mask = (~base_modern) & allow_transfer
    output = []
    for modern, transfer in zip(
        parents[linear_gate.MODERN_PARENT],
        parents[linear_gate.TRANSFER_PARENT],
        strict=True,
    ):
        scale = np.where(accepted, 1.0, np.where(rejected, FALLBACK_EXPOSURE, 0.0))
        values = np.where(
            base_modern, modern.values * scale, np.where(transfer_mask, transfer.values, 0.0)
        )
        benchmark = np.where(
            base_modern, modern.benchmark * scale, np.where(transfer_mask, transfer.benchmark, 0.0)
        )
        active = np.where(base_modern, modern.active, transfer_mask & transfer.active)
        trades = np.where(
            base_modern,
            modern.component_trades,
            np.where(transfer_mask, transfer.component_trades, 0),
        )
        output.append(v34.v12.ReturnStream(values, benchmark, active, trades))
    return tuple(output)


campaign.FIRST_VERSION = 6195
campaign.LAST_VERSION = 6294
campaign.PRIOR_COMPARISON_CELLS = 255_055
campaign.GATE_DECISION = 2
campaign.MECHANISM = "v4513_downside_sensitive_early_quality_half_fallback"
campaign.FACTOR_SETS = {
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
campaign._fit = _fit
linear_gate._route = _route


if __name__ == "__main__":
    campaign.main()
