"""v1463-v1562 preregistered intraday-path multi-factor campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v550_v649_state_gated_reversal as campaign
import numpy as np


class IntradayPathCube(campaign.prior.v53.Cube):
    """Add causal path-state factors not present in the frozen base cube."""

    def factors(self, decision: int) -> dict[str, np.ndarray]:
        output = super().factors(decision)
        if "drawdown_from_high" in output:
            return output

        closes = self.closes[:, : decision + 1, :]
        current = closes[:, -1, :]
        finite_close = np.isfinite(closes)
        valid_path = finite_close.any(axis=1)
        high = np.where(valid_path, np.where(finite_close, closes, -np.inf).max(axis=1), np.nan)
        low = np.where(valid_path, np.where(finite_close, closes, np.inf).min(axis=1), np.nan)
        drawdown = np.divide(current, high, out=np.full_like(current, np.nan), where=high > 0) - 1.0
        rebound = np.divide(current, low, out=np.full_like(current, np.nan), where=low > 0) - 1.0
        span = high - low
        range_position = np.divide(
            current - low,
            span,
            out=np.full_like(current, np.nan),
            where=span > 0,
        )

        returns = self.bar_return[:, : decision + 1, :]
        volume = self.bar_volume[:, : decision + 1, :]
        recent_start = max(1, decision - 3)
        earlier_returns = returns[:, :recent_start, :]
        recent_returns = returns[:, recent_start:, :]
        earlier_volume = volume[:, :recent_start, :]
        recent_volume = volume[:, recent_start:, :]

        def safe_mean(values: np.ndarray) -> np.ndarray:
            finite = np.isfinite(values)
            count = finite.sum(axis=1)
            return np.divide(
                np.where(finite, values, 0.0).sum(axis=1),
                count,
                out=np.full_like(current, np.nan),
                where=count > 0,
            )

        earlier_volatility = np.sqrt(np.nansum(earlier_returns**2, axis=1))
        recent_volatility = np.sqrt(np.nansum(recent_returns**2, axis=1))
        volatility_ratio = np.divide(
            recent_volatility,
            earlier_volatility,
            out=np.full_like(current, np.nan),
            where=earlier_volatility > 0,
        )
        earlier_mean_volume = safe_mean(earlier_volume)
        recent_mean_volume = safe_mean(recent_volume)
        volume_ratio = np.divide(
            recent_mean_volume,
            earlier_mean_volume,
            out=np.full_like(current, np.nan),
            where=earlier_mean_volume > 0,
        )
        return_acceleration = safe_mean(recent_returns) - safe_mean(earlier_returns)
        output.update(
            {
                "drawdown_from_high": drawdown,
                "rebound_from_low": rebound,
                "intraday_range_position": range_position,
                "recent_volatility_ratio": volatility_ratio,
                "recent_volume_ratio": volume_ratio,
                "return_acceleration": return_acceleration,
            }
        )
        return output


def main() -> None:
    campaign.FIRST_VERSION = 1463
    campaign.LAST_VERSION = 1562
    campaign.PRIOR_COMPARISON_CELLS = 81_155
    campaign.prior.v53.Cube = IntradayPathCube
    campaign.FAMILIES = (
        (
            "deep_drawdown_low_recovery",
            ("drawdown_from_high", "rebound_from_low", "intraday_range_position"),
            (-1, 1, 1),
        ),
        (
            "failed_breakdown_reclaim",
            ("drawdown_from_high", "recent_return", "return_acceleration"),
            (-1, 1, 1),
        ),
        (
            "high_hold_flow_continuation",
            ("drawdown_from_high", "path_efficiency", "signed_volume_imbalance"),
            (1, 1, 1),
        ),
        (
            "volatility_contraction_breakout",
            ("recent_volatility_ratio", "current_return", "path_efficiency"),
            (-1, 1, 1),
        ),
        (
            "volume_contraction_reacceleration",
            ("recent_volume_ratio", "return_acceleration", "relative_return"),
            (-1, 1, 1),
        ),
        (
            "quiet_pullback_reclaim",
            ("drawdown_from_high", "recent_volatility_ratio", "return_acceleration"),
            (-1, -1, 1),
        ),
        (
            "range_recovery_with_flow",
            ("intraday_range_position", "rebound_from_low", "signed_volume_imbalance"),
            (1, 1, 1),
        ),
        (
            "relative_laggard_path_turn",
            ("relative_return", "rebound_from_low", "return_acceleration"),
            (-1, 1, 1),
        ),
        (
            "compressed_rank_leadership",
            ("current_rank", "recent_volatility_ratio", "intraday_range_position"),
            (1, -1, 1),
        ),
        (
            "vwap_path_reacceleration",
            ("vwap_distance", "return_acceleration", "recent_volume_ratio"),
            (1, 1, -1),
        ),
    )
    campaign.SCHEDULES = ((23, 47), (29, 53), (35, 59), (41, 65), (47, 71))
    campaign.STATE_MODES = ("unfiltered", "orderly_rebound_cash_filter")
    campaign.main()


if __name__ == "__main__":
    main()
