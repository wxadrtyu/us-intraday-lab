"""Preregistered staged multi-session recovery multifactor campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v3369_v3468_multiday_exhaustion as exhaustion
import numpy as np
import search_full_universe_intraday_v12_robustness as v12

campaign = exhaustion.campaign
OPENING_END = 11


class StagedRecoveryCube(exhaustion.MultidayExhaustionCube):
    """Separate opening damage from the subsequent causal recovery stage."""

    def factors(self, decision: int) -> dict[str, np.ndarray]:
        output = super().factors(decision)
        if "recovery_stage_return" in output:
            return output
        opening_prices = self.closes[:, : OPENING_END + 1, :]
        opening_start = self.opens[:, 0, :]
        opening_end = self.closes[:, OPENING_END, :]
        current = self.closes[:, decision, :]
        opening_return = opening_end / opening_start - 1.0
        finite_opening = np.isfinite(opening_prices)
        valid_opening = finite_opening.any(axis=1)
        opening_low = np.where(
            valid_opening,
            np.where(finite_opening, opening_prices, np.inf).min(axis=1),
            np.nan,
        )
        opening_drawdown = opening_low / opening_start - 1.0
        recovery_return = current / opening_end - 1.0
        recovery_from_low = current / opening_low - 1.0

        recovery_bars = self.bar_return[:, OPENING_END + 1 : decision + 1, :]
        finite_recovery = np.isfinite(recovery_bars)
        recovery_path = np.where(finite_recovery, np.abs(recovery_bars), 0.0).sum(axis=1)
        recovery_efficiency = np.divide(
            recovery_return,
            recovery_path,
            out=np.full_like(recovery_return, np.nan),
            where=recovery_path > 1e-8,
        )
        earlier_vwap = self._micro(decision - 3)["price_vwap"]
        vwap_slope = output["vwap_distance"] - earlier_vwap

        early_current = self._features(OPENING_END)["current"]
        current_features = self._features(decision)["current"]
        def positive_fraction(values: np.ndarray, minimum: int) -> np.ndarray:
            finite = np.isfinite(values)
            count = finite.sum(axis=1)
            return np.divide(
                ((values > 0.0) & finite).sum(axis=1),
                count,
                out=np.full(len(values), np.nan),
                where=count >= minimum,
            )

        early_breadth = positive_fraction(early_current[:, v12.SECTORS], 7)
        current_breadth = positive_fraction(current_features[:, v12.SECTORS], 7)
        breadth_repair = current_breadth - early_breadth
        early_agreement = positive_fraction(early_current[:, (0, 1, 2)], 3)
        current_agreement = positive_fraction(current_features[:, (0, 1, 2)], 3)
        agreement_repair = current_agreement - early_agreement

        recovery_volume = self.bar_volume[:, OPENING_END + 1 : decision + 1, :]
        signed_recovery_volume = np.where(
            finite_recovery,
            np.sign(recovery_bars) * recovery_volume,
            0.0,
        ).sum(axis=1)
        total_recovery_volume = np.where(np.isfinite(recovery_volume), recovery_volume, 0.0).sum(
            axis=1
        )
        recovery_flow = np.divide(
            signed_recovery_volume,
            total_recovery_volume,
            out=np.full_like(recovery_return, np.nan),
            where=total_recovery_volume > 0,
        )

        def repeat(values: np.ndarray) -> np.ndarray:
            return np.repeat(values[:, None], current.shape[1], axis=1)

        output.update(
            {
                "opening_stage_return": opening_return,
                "opening_stage_drawdown": opening_drawdown,
                "recovery_stage_return": recovery_return,
                "recovery_from_opening_low": recovery_from_low,
                "recovery_efficiency": recovery_efficiency,
                "vwap_reclaim_slope": vwap_slope,
                "sector_breadth_repair": repeat(breadth_repair),
                "risk_agreement_repair": repeat(agreement_repair),
                "recovery_flow_imbalance": recovery_flow,
            }
        )
        return output


def configure() -> None:
    campaign.FIRST_VERSION = 3469
    campaign.LAST_VERSION = 3568
    campaign.PRIOR_COMPARISON_CELLS = 163_305
    campaign.prior.v53.Cube = StagedRecoveryCube
    campaign.HISTORICAL_MIN_ANNUALIZED_RETURN = 0.15
    campaign.REQUIRE_CONSUMED_2026Q1_GATE = True
    campaign.FAMILIES = (
        (
            "three_day_staged_recovery",
            ("prior3_return", "opening_stage_drawdown", "recovery_stage_return", "recovery_efficiency"),
            (-1, -1, 1, 1),
        ),
        (
            "five_day_staged_recovery",
            ("prior5_return", "opening_stage_return", "recovery_from_opening_low", "return_acceleration"),
            (-1, -1, 1, 1),
        ),
        (
            "opening_drawdown_repair",
            ("opening_stage_drawdown", "recovery_from_opening_low", "vwap_reclaim_slope", "close_location"),
            (-1, 1, 1, 1),
        ),
        (
            "breadth_repaired_exhaustion",
            ("prior3_return", "recovery_stage_return", "sector_breadth_repair", "risk_agreement_repair"),
            (-1, 1, 1, 1),
        ),
        (
            "vwap_slope_recovery",
            ("prior5_return", "vwap_reclaim_slope", "recovery_efficiency", "signed_volume_imbalance"),
            (-1, 1, 1, 1),
        ),
        (
            "efficient_multiday_recovery",
            ("short_long_exhaustion", "recovery_efficiency", "recovery_stage_return", "path_efficiency"),
            (-1, 1, 1, 1),
        ),
        (
            "flow_turn_recovery",
            ("prior3_return", "opening_stage_drawdown", "recovery_flow_imbalance", "volume_acceleration"),
            (-1, -1, 1, -1),
        ),
        (
            "risk_agreement_recovery",
            ("prior5_downside_volatility", "recovery_stage_return", "risk_agreement_repair", "sector_breadth_repair"),
            (1, 1, 1, 1),
        ),
        (
            "short_long_staged_turn",
            ("short_long_exhaustion", "opening_stage_return", "return_acceleration", "vwap_reclaim_slope"),
            (-1, -1, 1, 1),
        ),
        (
            "staged_recovery_consensus",
            ("prior3_return", "opening_stage_drawdown", "recovery_stage_return", "recovery_efficiency", "recovery_flow_imbalance"),
            (-1, -1, 1, 1, 1),
        ),
    )
    campaign.SCHEDULES = ((20, 47), (23, 50), (23, 53), (26, 53), (29, 56))
    campaign.STATE_MODES = ("unfiltered", "orderly_rebound_cash_filter")


if __name__ == "__main__":
    configure()
    campaign.main()
