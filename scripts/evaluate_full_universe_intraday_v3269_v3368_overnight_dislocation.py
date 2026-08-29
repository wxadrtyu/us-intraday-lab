"""Preregistered overnight-dislocation multifactor campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v1463_v1562_intraday_path_multifactor as path
import numpy as np

campaign = path.campaign


class OvernightDislocationCube(path.IntradayPathCube):
    """Add causal gap-normalization and gap-repair factors."""

    def factors(self, decision: int) -> dict[str, np.ndarray]:
        output = super().factors(decision)
        if "normalized_gap" in output:
            return output

        current = output["current_return"]
        gap = output["gap"]
        prior1 = output["prior1_return"]
        windows = np.lib.stride_tricks.sliding_window_view(self.prior1, 20, axis=0)
        valid_window = np.isfinite(windows).all(axis=-1)
        rolling_volatility = np.where(valid_window, np.std(windows, axis=-1, ddof=1), np.nan)
        trailing_volatility = np.full_like(current, np.nan)
        trailing_volatility[19:] = rolling_volatility
        normalized_gap = np.divide(
            gap,
            trailing_volatility,
            out=np.full_like(gap, np.nan),
            where=trailing_volatility > 0,
        )
        gap_scale = np.abs(gap)
        fill_progress = np.divide(
            -np.sign(gap) * current,
            gap_scale,
            out=np.full_like(gap, np.nan),
            where=gap_scale > 1e-8,
        )
        gap_persistence = np.sign(gap) * current
        gap_remaining = (1.0 + gap) * (1.0 + current) - 1.0
        prior_reversal = -np.sign(prior1) * current
        gap_prior_agreement = np.sign(gap) * np.sign(prior1)
        fill_acceleration = -np.sign(gap) * output["return_acceleration"]
        output.update(
            {
                "normalized_gap": normalized_gap,
                "negative_gap_shock": -normalized_gap,
                "positive_gap_shock": normalized_gap,
                "gap_fill_progress": fill_progress,
                "gap_persistence": gap_persistence,
                "gap_remaining": gap_remaining,
                "prior_reversal_alignment": prior_reversal,
                "gap_prior_agreement": gap_prior_agreement,
                "gap_fill_acceleration": fill_acceleration,
                "trailing_daily_volatility": trailing_volatility,
            }
        )
        return output


def configure() -> None:
    campaign.FIRST_VERSION = 3269
    campaign.LAST_VERSION = 3368
    campaign.PRIOR_COMPARISON_CELLS = 137_705
    campaign.prior.v53.Cube = OvernightDislocationCube
    campaign.HISTORICAL_MIN_ANNUALIZED_RETURN = 0.15
    campaign.REQUIRE_CONSUMED_2026Q1_GATE = True
    campaign.FAMILIES = (
        (
            "negative_gap_fill",
            ("negative_gap_shock", "gap_fill_progress", "gap_fill_acceleration", "close_location"),
            (1, 1, 1, 1),
        ),
        (
            "positive_gap_hold",
            ("positive_gap_shock", "gap_persistence", "path_efficiency", "signed_volume_imbalance"),
            (1, 1, 1, 1),
        ),
        (
            "prior_loss_gap_recovery",
            ("prior1_return", "negative_gap_shock", "prior_reversal_alignment", "recent_return"),
            (-1, 1, 1, 1),
        ),
        (
            "double_weakness_repair",
            ("prior20_return", "negative_gap_shock", "gap_fill_progress", "return_acceleration"),
            (-1, 1, 1, 1),
        ),
        (
            "gap_fill_flow_confirmation",
            ("gap_fill_progress", "signed_volume_imbalance", "volume_acceleration", "vwap_distance"),
            (1, 1, -1, 1),
        ),
        (
            "quiet_gap_fade",
            ("normalized_gap", "trailing_daily_volatility", "gap_fill_progress", "realized_volatility"),
            (-1, -1, 1, -1),
        ),
        (
            "breadth_confirmed_gap_follow",
            ("positive_gap_shock", "gap_persistence", "sector_breadth", "risk_asset_agreement"),
            (1, 1, 1, 1),
        ),
        (
            "prior_gap_disagreement_turn",
            ("gap_prior_agreement", "prior_reversal_alignment", "gap_fill_acceleration", "close_location"),
            (-1, 1, 1, 1),
        ),
        (
            "remaining_gap_laggard_reclaim",
            ("gap_remaining", "relative_return", "gap_fill_progress", "current_rank"),
            (-1, -1, 1, -1),
        ),
        (
            "shock_repair_consensus",
            ("negative_gap_shock", "gap_fill_progress", "gap_fill_acceleration", "prior_reversal_alignment", "signed_volume_imbalance"),
            (1, 1, 1, 1, 1),
        ),
    )
    campaign.SCHEDULES = ((17, 41), (20, 47), (23, 53), (29, 59), (35, 65))
    campaign.STATE_MODES = ("unfiltered", "orderly_rebound_cash_filter")


if __name__ == "__main__":
    configure()
    campaign.main()
