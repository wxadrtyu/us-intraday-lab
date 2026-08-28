"""v1966-v2065: state-transition enhancements and independent exhaustion/recovery."""

from __future__ import annotations

import evaluate_full_universe_intraday_v349_v448_preregistered_campaign as campaign
import numpy as np

campaign.FIRST_VERSION = 1966
campaign.LAST_VERSION = 2065
campaign.PRIOR_COMPARISON_CELLS = 111_005
# Reuse the 25 declared v349 concept directions, but test changes rather than
# state levels. These are two new causal structures, not parameter renumbering.
campaign.STATE_CLOCKS = ("opening_change_from_prior_close", "prior_close_change")
campaign.RULE_FAMILIES = (
    (
        "crowded_gap_distribution_recovery",
        ("gap", "current_rank", "signed_volume_imbalance", "recent_return"),
        (-1, -1, 1, 1),
    ),
    (
        "failed_breakout_absorption",
        ("current_return", "close_location", "signed_volume_imbalance", "volume_acceleration"),
        (-1, 1, 1, -1),
    ),
    (
        "long_trend_short_pullback",
        ("prior20_return", "recent_return", "vwap_distance", "path_efficiency"),
        (1, -1, -1, 1),
    ),
    (
        "liquidity_exhaustion_rebound",
        ("volume_acceleration", "realized_volatility", "recent_return", "close_location"),
        (-1, 1, -1, 1),
    ),
    (
        "leveraged_discount_flow_repair",
        ("leverage_residual", "signed_volume_imbalance", "current_rank", "vwap_distance"),
        (-1, 1, -1, 1),
    ),
    (
        "overnight_shock_intraday_stabilization",
        ("gap", "realized_volatility", "path_efficiency", "relative_return"),
        (-1, -1, 1, 1),
    ),
    (
        "prior_winner_orderly_retest",
        ("prior20_rank", "vwap_distance", "realized_volatility", "close_location"),
        (1, -1, -1, 1),
    ),
    (
        "unpopular_asset_flow_rotation",
        ("prior20_rank", "current_rank", "signed_volume_imbalance", "volume_acceleration"),
        (-1, -1, 1, 1),
    ),
    (
        "relative_laggard_compression_repair",
        ("relative_return", "realized_volatility", "recent_return", "path_efficiency"),
        (-1, -1, 1, 1),
    ),
    (
        "trend_exhaustion_vwap_support",
        ("prior20_return", "current_return", "vwap_distance", "signed_volume_imbalance"),
        (1, -1, 1, 1),
    ),
)
# Opening stabilization; late morning; lunch; afternoon reset; close-window.
campaign.RULE_SCHEDULES = ((9, 28), (21, 43), (33, 55), (45, 69), (58, 77))

_base_matrix = campaign.prior._state_matrix


def _lag(values: np.ndarray) -> np.ndarray:
    return np.concatenate((np.array([np.nan]), values[:-1]))


def transition_matrix(cube, clock: str) -> dict[str, np.ndarray]:
    """No current-day close enters an opening decision; missing inputs stay NaN."""
    previous = _base_matrix(cube, "prior_close")
    if clock == "opening_change_from_prior_close":
        current = _base_matrix(cube, "bar17")
        return {name: current[name] - previous[name] for name in previous}
    if clock == "prior_close_change":
        return {name: value - _lag(value) for name, value in previous.items()}
    raise ValueError("undeclared state-transition clock")


def configure() -> None:
    campaign.prior._state_matrix = transition_matrix


if __name__ == "__main__":
    configure()
    campaign.main()
