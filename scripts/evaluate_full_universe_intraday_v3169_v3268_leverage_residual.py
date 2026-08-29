"""Paired leveraged/underlying residual multifactor campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v1463_v1562_intraday_path_multifactor as path
import numpy as np

campaign = path.campaign
LEVERAGED = np.array((3, 4))
UNDERLYING = np.array((1, 10))


class ResidualCube(path.IntradayPathCube):
    def factors(self, decision: int) -> dict[str, np.ndarray]:
        output = super().factors(decision)
        if "paired_leverage_residual" in output:
            return output
        current = output["current_return"]
        recent = output["recent_return"]
        residual = current[:, LEVERAGED] - 3.0 * current[:, UNDERLYING]
        recent_residual = recent[:, LEVERAGED] - 3.0 * recent[:, UNDERLYING]
        returns = self.bar_return[:, : decision + 1, :]
        recent_start = max(1, decision - 3)

        def time_mean(values: np.ndarray) -> np.ndarray:
            finite = np.isfinite(values)
            count = finite.sum(axis=1)
            return np.divide(
                np.where(finite, values, 0.0).sum(axis=1),
                count,
                out=np.full((len(values), values.shape[2]), np.nan),
                where=count > 0,
            )

        recent_bar_mean = time_mean(returns[:, recent_start:, :])
        earlier_bar_mean = time_mean(returns[:, :recent_start, :])
        recent_bar_residual = (
            recent_bar_mean[:, LEVERAGED] - 3.0 * recent_bar_mean[:, UNDERLYING]
        )
        earlier_bar_residual = (
            earlier_bar_mean[:, LEVERAGED] - 3.0 * earlier_bar_mean[:, UNDERLYING]
        )
        acceleration = recent_bar_residual - earlier_bar_residual
        underlying = current[:, UNDERLYING]
        valid_pair = np.isfinite(underlying).all(axis=1)
        underlying_mean = np.where(valid_pair, underlying.sum(axis=1) / 2.0, np.nan)
        underlying_relative = underlying - underlying_mean[:, None]
        valid_residual = np.isfinite(residual).all(axis=1)
        dispersion = np.where(valid_residual, np.ptp(residual, axis=1), np.nan)
        rank = np.where(
            np.isfinite(residual).all(axis=1)[:, None],
            1.0 + (residual > residual[:, ::-1]).astype(float),
            np.nan,
        ) / 2.0
        agreement = np.where(
            np.isfinite(current[:, LEVERAGED]) & np.isfinite(current[:, UNDERLYING]),
            (np.sign(current[:, LEVERAGED]) == np.sign(current[:, UNDERLYING])).astype(float),
            np.nan,
        )

        def leveraged_only(values: np.ndarray) -> np.ndarray:
            result = np.full_like(current, np.nan)
            result[:, LEVERAGED] = values
            return result

        output.update(
            {
                "paired_leverage_residual": leveraged_only(residual),
                "paired_recent_residual": leveraged_only(recent_residual),
                "residual_acceleration": leveraged_only(acceleration),
                "underlying_relative_strength": leveraged_only(underlying_relative),
                "cross_residual_dispersion": leveraged_only(
                    np.repeat(dispersion[:, None], 2, axis=1)
                ),
                "cross_residual_rank": leveraged_only(rank),
                "underlying_direction_agreement": leveraged_only(agreement),
            }
        )
        return output


def configure() -> None:
    campaign.FIRST_VERSION = 3169
    campaign.LAST_VERSION = 3268
    campaign.PRIOR_COMPARISON_CELLS = 124_905
    campaign.prior.v53.Cube = ResidualCube
    campaign.HISTORICAL_MIN_ANNUALIZED_RETURN = 0.15
    campaign.REQUIRE_CONSUMED_2026Q1_GATE = True
    campaign.FAMILIES = (
        (
            "residual_reversal",
            ("paired_leverage_residual", "paired_recent_residual", "close_location"),
            (-1, 1, 1),
        ),
        (
            "residual_continuation",
            ("paired_leverage_residual", "paired_recent_residual", "path_efficiency"),
            (1, 1, 1),
        ),
        (
            "residual_laggard_underlying_strength",
            (
                "paired_leverage_residual",
                "underlying_relative_strength",
                "paired_recent_residual",
                "close_location",
            ),
            (-1, 1, 1, 1),
        ),
        (
            "residual_leader_underlying_confirmation",
            (
                "paired_leverage_residual",
                "underlying_relative_strength",
                "signed_volume_imbalance",
                "underlying_direction_agreement",
            ),
            (1, 1, 1, 1),
        ),
        (
            "dispersion_reversal",
            ("cross_residual_dispersion", "cross_residual_rank", "paired_recent_residual"),
            (1, -1, 1),
        ),
        (
            "dispersion_continuation",
            ("cross_residual_dispersion", "cross_residual_rank", "signed_volume_imbalance"),
            (1, 1, 1),
        ),
        (
            "underlying_rotation",
            ("underlying_relative_strength", "paired_recent_residual", "current_rank"),
            (1, 1, 1),
        ),
        (
            "residual_flow_absorption",
            (
                "paired_leverage_residual",
                "signed_volume_imbalance",
                "volume_acceleration",
                "close_location",
            ),
            (-1, 1, -1, 1),
        ),
        (
            "residual_volatility_contraction",
            ("paired_leverage_residual", "realized_volatility", "residual_acceleration"),
            (-1, -1, 1),
        ),
        (
            "residual_breakout_confirmation",
            ("paired_leverage_residual", "residual_acceleration", "vwap_distance"),
            (1, 1, 1),
        ),
    )
    campaign.SCHEDULES = ((20, 35), (23, 41), (29, 47), (35, 59), (41, 65))
    campaign.STATE_MODES = ("unfiltered", "orderly_rebound_cash_filter")


if __name__ == "__main__":
    configure()
    campaign.main()
