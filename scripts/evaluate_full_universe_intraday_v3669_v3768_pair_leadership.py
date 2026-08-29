"""Preregistered TQQQ/SOXL pair-leadership multifactor campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v3369_v3468_multiday_exhaustion as exhaustion
import numpy as np

campaign = exhaustion.campaign
ASSETS = np.array((3, 4))
UNDERLYINGS = np.array((1, 10))


class PairLeadershipCube(exhaustion.MultidayExhaustionCube):
    """Add signed pair leadership mapped to each eligible leveraged ETF."""

    def factors(self, decision: int) -> dict[str, np.ndarray]:
        output = super().factors(decision)
        if "pair_leadership" in output:
            return output
        current = output["current_return"]
        recent = output["recent_return"]
        acceleration = output["return_acceleration"]
        prior3 = output["prior3_return"]

        def signed_pair(values: np.ndarray, indexes: np.ndarray) -> np.ndarray:
            relative = values[:, indexes[0]] - values[:, indexes[1]]
            mapped = np.full_like(current, np.nan)
            mapped[:, ASSETS[0]] = relative
            mapped[:, ASSETS[1]] = -relative
            return mapped

        pair = signed_pair(current, ASSETS)
        pair_recent = signed_pair(recent, ASSETS)
        pair_acceleration = signed_pair(acceleration, ASSETS)
        pair_prior3 = signed_pair(prior3, ASSETS)
        underlying = signed_pair(current, UNDERLYINGS)
        pair_relative = current[:, ASSETS[0]] - current[:, ASSETS[1]]
        underlying_relative = current[:, UNDERLYINGS[0]] - current[:, UNDERLYINGS[1]]
        valid = np.isfinite(pair_relative) & np.isfinite(underlying_relative)
        agreement = np.where(
            valid,
            (np.sign(pair_relative) == np.sign(underlying_relative)).astype(float),
            np.nan,
        )
        dispersion = np.where(np.isfinite(pair_relative), np.abs(pair_relative), np.nan)

        def repeat_on_assets(values: np.ndarray) -> np.ndarray:
            mapped = np.full_like(current, np.nan)
            mapped[:, ASSETS] = values[:, None]
            return mapped

        output.update(
            {
                "pair_leadership": pair,
                "pair_recent_leadership": pair_recent,
                "pair_leadership_acceleration": pair_acceleration,
                "pair_prior3_leadership": pair_prior3,
                "underlying_pair_leadership": underlying,
                "pair_underlying_agreement": repeat_on_assets(agreement),
                "pair_dispersion": repeat_on_assets(dispersion),
            }
        )
        return output


def configure() -> None:
    campaign.FIRST_VERSION = 3669
    campaign.LAST_VERSION = 3768
    campaign.PRIOR_COMPARISON_CELLS = 188_905
    campaign.prior.v53.Cube = PairLeadershipCube
    campaign.HISTORICAL_MIN_ANNUALIZED_RETURN = 0.15
    campaign.REQUIRE_CONSUMED_2026Q1_GATE = True
    campaign.FAMILIES = (
        (
            "pair_winner_continuation",
            ("pair_leadership", "pair_recent_leadership", "current_return", "path_efficiency"),
            (1, 1, 1, 1),
        ),
        (
            "underlying_confirmed_winner",
            ("pair_leadership", "underlying_pair_leadership", "pair_underlying_agreement", "current_return"),
            (1, 1, 1, 1),
        ),
        (
            "flow_confirmed_winner",
            ("pair_leadership", "pair_recent_leadership", "signed_volume_imbalance", "volume_acceleration"),
            (1, 1, 1, -1),
        ),
        (
            "low_volatility_winner",
            ("pair_leadership", "realized_volatility", "path_efficiency", "close_location"),
            (1, -1, 1, 1),
        ),
        (
            "prior3_leadership_rotation",
            ("pair_prior3_leadership", "pair_leadership", "pair_recent_leadership", "relative_return"),
            (1, 1, 1, 1),
        ),
        (
            "leadership_acceleration",
            ("pair_leadership", "pair_leadership_acceleration", "recent_return", "vwap_distance"),
            (1, 1, 1, 1),
        ),
        (
            "leader_pullback_reentry",
            ("pair_leadership", "pair_recent_leadership", "close_location", "return_acceleration"),
            (1, -1, 1, 1),
        ),
        (
            "dispersion_breakout",
            ("pair_dispersion", "pair_leadership", "path_efficiency", "signed_volume_imbalance"),
            (1, 1, 1, 1),
        ),
        (
            "breadth_confirmed_winner",
            ("pair_leadership", "underlying_pair_leadership", "sector_breadth", "risk_asset_agreement"),
            (1, 1, 1, 1),
        ),
        (
            "pair_leadership_consensus",
            ("pair_leadership", "pair_recent_leadership", "underlying_pair_leadership", "pair_underlying_agreement", "signed_volume_imbalance"),
            (1, 1, 1, 1, 1),
        ),
    )
    campaign.SCHEDULES = ((17, 41), (23, 53), (29, 59), (35, 65), (41, 72))
    campaign.STATE_MODES = ("unfiltered", "orderly_rebound_cash_filter")


if __name__ == "__main__":
    configure()
    campaign.main()
