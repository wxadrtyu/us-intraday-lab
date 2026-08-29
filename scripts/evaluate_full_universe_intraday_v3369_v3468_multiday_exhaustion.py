"""Preregistered multi-session exhaustion/recovery multifactor campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v1463_v1562_intraday_path_multifactor as path
import numpy as np

campaign = path.campaign


def _rolling_compound(values: np.ndarray, window: int) -> np.ndarray:
    result = np.full_like(values, np.nan)
    windows = np.lib.stride_tricks.sliding_window_view(values, window, axis=0)
    valid = np.isfinite(windows).all(axis=-1)
    compounded = np.prod(1.0 + np.where(np.isfinite(windows), windows, 0.0), axis=-1) - 1.0
    result[window - 1 :] = np.where(valid, compounded, np.nan)
    return result


class MultidayExhaustionCube(path.IntradayPathCube):
    """Add causal short-horizon daily-path factors."""

    def factors(self, decision: int) -> dict[str, np.ndarray]:
        output = super().factors(decision)
        if "prior3_return" in output:
            return output
        prior3 = _rolling_compound(self.prior1, 3)
        prior5 = _rolling_compound(self.prior1, 5)
        windows5 = np.lib.stride_tricks.sliding_window_view(self.prior1, 5, axis=0)
        valid5 = np.isfinite(windows5).all(axis=-1)
        loss_share_values = np.mean(windows5 < 0.0, axis=-1)
        downside_values = np.sqrt(np.sum(np.minimum(windows5, 0.0) ** 2, axis=-1))
        loss_share = np.full_like(self.prior1, np.nan)
        downside_volatility = np.full_like(self.prior1, np.nan)
        loss_share[4:] = np.where(valid5, loss_share_values, np.nan)
        downside_volatility[4:] = np.where(valid5, downside_values, np.nan)

        prior_intraday = np.full_like(self.prior1, np.nan)
        prior_late = np.full_like(self.prior1, np.nan)
        daily_intraday = self.closes[:, 77, :] / self.opens[:, 0, :] - 1.0
        daily_late = self.closes[:, 77, :] / self.opens[:, 65, :] - 1.0
        prior_intraday[1:] = daily_intraday[:-1]
        prior_late[1:] = daily_late[:-1]
        current = output["current_return"]
        output.update(
            {
                "prior3_return": prior3,
                "prior5_return": prior5,
                "prior5_loss_share": loss_share,
                "prior5_downside_volatility": downside_volatility,
                "prior_session_intraday_return": prior_intraday,
                "prior_session_late_return": prior_late,
                "short_long_exhaustion": prior3 - 0.15 * output["prior20_return"],
                "multiday_reversal_alignment": -np.sign(prior3) * current,
            }
        )
        return output


def configure() -> None:
    campaign.FIRST_VERSION = 3369
    campaign.LAST_VERSION = 3468
    campaign.PRIOR_COMPARISON_CELLS = 150_505
    campaign.prior.v53.Cube = MultidayExhaustionCube
    campaign.HISTORICAL_MIN_ANNUALIZED_RETURN = 0.15
    campaign.REQUIRE_CONSUMED_2026Q1_GATE = True
    campaign.FAMILIES = (
        (
            "three_day_crash_rebound",
            ("prior3_return", "multiday_reversal_alignment", "recent_return", "close_location"),
            (-1, 1, 1, 1),
        ),
        (
            "five_day_exhaustion_recovery",
            ("prior5_return", "prior5_loss_share", "return_acceleration", "path_efficiency"),
            (-1, 1, 1, 1),
        ),
        (
            "loss_streak_stabilization",
            ("prior5_loss_share", "recent_volatility_ratio", "recent_return", "close_location"),
            (1, -1, 1, 1),
        ),
        (
            "short_long_oversold_turn",
            ("short_long_exhaustion", "prior20_return", "return_acceleration", "vwap_distance"),
            (-1, -1, 1, 1),
        ),
        (
            "prior_late_capitulation_repair",
            ("prior_session_late_return", "gap", "recent_return", "signed_volume_imbalance"),
            (-1, -1, 1, 1),
        ),
        (
            "downside_volatility_stabilization",
            ("prior5_downside_volatility", "realized_volatility", "return_acceleration", "close_location"),
            (1, -1, 1, 1),
        ),
        (
            "prior_intraday_loss_gap_resilience",
            ("prior_session_intraday_return", "gap", "current_return", "path_efficiency"),
            (-1, 1, 1, 1),
        ),
        (
            "multiday_relative_rebound",
            ("prior3_return", "relative_return", "current_rank", "multiday_reversal_alignment"),
            (-1, 1, 1, 1),
        ),
        (
            "flow_confirmed_crash_rebound",
            ("prior5_return", "signed_volume_imbalance", "volume_acceleration", "recent_return"),
            (-1, 1, -1, 1),
        ),
        (
            "breadth_confirmed_exhaustion_turn",
            ("prior3_return", "multiday_reversal_alignment", "sector_breadth", "risk_asset_agreement"),
            (-1, 1, 1, 1),
        ),
    )
    campaign.SCHEDULES = ((11, 35), (17, 41), (23, 53), (29, 59), (35, 65))
    campaign.STATE_MODES = ("unfiltered", "orderly_rebound_cash_filter")


if __name__ == "__main__":
    configure()
    campaign.main()
