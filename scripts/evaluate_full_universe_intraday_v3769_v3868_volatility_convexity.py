"""Preregistered leveraged-ETF volatility/convexity multifactor campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v3369_v3468_multiday_exhaustion as exhaustion
import numpy as np

campaign = exhaustion.campaign
ASSETS = np.array((3, 4))
UNDERLYINGS = np.array((1, 10))


class VolatilityConvexityCube(exhaustion.MultidayExhaustionCube):
    """Add asset-specific leverage residual and volatility-state factors."""

    def factors(self, decision: int) -> dict[str, np.ndarray]:
        output = super().factors(decision)
        if "volatility_multiple" in output:
            return output

        current = output["current_return"]

        def asset_residual(values: np.ndarray, multiplier: float = 3.0) -> np.ndarray:
            mapped = np.full_like(current, np.nan)
            mapped[:, ASSETS] = values[:, ASSETS] - multiplier * values[:, UNDERLYINGS]
            return mapped

        def asset_ratio(numerator: np.ndarray, denominator: np.ndarray) -> np.ndarray:
            mapped = np.full_like(current, np.nan)
            mapped[:, ASSETS] = np.divide(
                numerator[:, ASSETS],
                denominator[:, UNDERLYINGS],
                out=np.full((current.shape[0], len(ASSETS)), np.nan),
                where=denominator[:, UNDERLYINGS] > 1e-8,
            )
            return mapped

        def map_underlying(values: np.ndarray) -> np.ndarray:
            mapped = np.full_like(current, np.nan)
            mapped[:, ASSETS] = values[:, UNDERLYINGS]
            return mapped

        leverage_residual = asset_residual(current)
        recent_leverage_residual = asset_residual(output["recent_return"])
        prior3_leverage_residual = asset_residual(output["prior3_return"])
        volatility_multiple = asset_ratio(
            output["realized_volatility"], output["realized_volatility"]
        )
        path_efficiency_spread = asset_residual(output["path_efficiency"], multiplier=1.0)
        underlying_current = map_underlying(current)
        underlying_recent = map_underlying(output["recent_return"])
        convexity_turn = recent_leverage_residual - leverage_residual
        output.update(
            {
                "leverage_residual": leverage_residual,
                "recent_leverage_residual": recent_leverage_residual,
                "prior3_leverage_residual": prior3_leverage_residual,
                "volatility_multiple": volatility_multiple,
                "path_efficiency_spread": path_efficiency_spread,
                "underlying_current_return": underlying_current,
                "underlying_recent_return": underlying_recent,
                "convexity_turn": convexity_turn,
            }
        )
        return output


def configure() -> None:
    campaign.FIRST_VERSION = 3769
    campaign.LAST_VERSION = 3868
    campaign.PRIOR_COMPARISON_CELLS = 201_705
    campaign.prior.v53.Cube = VolatilityConvexityCube
    campaign.HISTORICAL_MIN_ANNUALIZED_RETURN = 0.15
    campaign.REQUIRE_CONSUMED_2026Q1_GATE = True
    campaign.FAMILIES = (
        (
            "positive_convexity_continuation",
            ("leverage_residual", "recent_leverage_residual", "underlying_current_return", "path_efficiency"),
            (1, 1, 1, 1),
        ),
        (
            "negative_convexity_repair",
            ("leverage_residual", "convexity_turn", "recent_return", "close_location"),
            (-1, 1, 1, 1),
        ),
        (
            "quiet_positive_convexity",
            ("leverage_residual", "volatility_multiple", "realized_volatility", "path_efficiency"),
            (1, -1, -1, 1),
        ),
        (
            "underlying_confirmed_convexity",
            ("leverage_residual", "underlying_current_return", "underlying_recent_return", "signed_volume_imbalance"),
            (1, 1, 1, 1),
        ),
        (
            "prior_convexity_reversal",
            ("prior3_leverage_residual", "leverage_residual", "return_acceleration", "close_location"),
            (-1, 1, 1, 1),
        ),
        (
            "volatility_expansion_follow",
            ("volatility_multiple", "leverage_residual", "underlying_current_return", "volume_acceleration"),
            (1, 1, 1, -1),
        ),
        (
            "volatility_compression_breakout",
            ("volatility_multiple", "recent_volatility_ratio", "return_acceleration", "signed_volume_imbalance"),
            (-1, -1, 1, 1),
        ),
        (
            "efficient_leverage_path",
            ("path_efficiency_spread", "path_efficiency", "leverage_residual", "vwap_distance"),
            (1, 1, 1, 1),
        ),
        (
            "breadth_confirmed_convexity",
            ("leverage_residual", "underlying_current_return", "sector_breadth", "risk_asset_agreement"),
            (1, 1, 1, 1),
        ),
        (
            "convexity_state_consensus",
            ("leverage_residual", "recent_leverage_residual", "convexity_turn", "volatility_multiple", "underlying_current_return"),
            (1, 1, 1, -1, 1),
        ),
    )
    campaign.SCHEDULES = ((11, 35), (17, 41), (23, 53), (29, 59), (35, 65))
    campaign.STATE_MODES = ("unfiltered", "orderly_rebound_cash_filter")


if __name__ == "__main__":
    configure()
    campaign.main()
