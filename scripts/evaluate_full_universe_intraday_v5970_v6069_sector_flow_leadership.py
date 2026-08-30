"""v5970-v6069 preregistered ETF sector-flow and leadership campaign."""

from __future__ import annotations

import evaluate_full_universe_intraday_v5670_v5769_modern_quality_gate as campaign
import numpy as np
import search_full_universe_intraday_v12_robustness as v12
from evaluate_full_universe_intraday_v1463_v1562_intraday_path_multifactor import (
    IntradayPathCube,
)

FIRST_VERSION = 5970
LAST_VERSION = 6069
PRIOR_COMPARISON_CELLS = 254_605
GATE_DECISION = 17
MODERN_ENTRY = 24
QUANTILES = (0.0, 0.2, 0.4, 0.6, 0.8)
ALPHAS = (1.0, 100.0)

FACTOR_SETS = {
    "broad_flow_confirmation": (
        "sector_signed_flow_breadth",
        "sector_return_flow_agreement",
        "sector_path_efficiency_breadth",
    ),
    "growth_flow_rotation": (
        "growth_minus_defensive_return",
        "growth_minus_defensive_flow",
        "sector_breadth_acceleration",
    ),
    "leadership_quality": (
        "sector_leadership_spread",
        "sector_leadership_concentration",
        "sector_return_flow_agreement",
    ),
    "contraction_release": (
        "sector_volatility_contraction",
        "sector_breadth_acceleration",
        "sector_signed_flow_breadth",
    ),
    "flow_dispersion_breakout": (
        "sector_flow_dispersion",
        "sector_leadership_spread",
        "sector_path_efficiency_breadth",
    ),
    "rotation_with_market": (
        "growth_minus_defensive_return",
        "growth_minus_defensive_flow",
        "spy_current",
        "sector_breadth",
    ),
    "efficient_participation": (
        "sector_path_efficiency_breadth",
        "sector_return_flow_agreement",
        "sector_breadth",
        "sector_dispersion",
    ),
    "quiet_broadening": (
        "sector_volatility_contraction",
        "sector_breadth_acceleration",
        "sector_flow_dispersion",
        "sector_signed_flow_breadth",
    ),
    "tech_leadership_flow": (
        "tech_minus_market",
        "growth_minus_defensive_flow",
        "sector_leadership_concentration",
        "sector_return_flow_agreement",
    ),
    "balanced_sector_state": (
        "sector_signed_flow_breadth",
        "sector_return_flow_agreement",
        "sector_path_efficiency_breadth",
        "sector_breadth_acceleration",
        "sector_volatility_contraction",
        "growth_minus_defensive_return",
        "growth_minus_defensive_flow",
        "sector_leadership_spread",
        "sector_leadership_concentration",
        "sector_flow_dispersion",
    ),
}


def _safe_mean(values: np.ndarray, axis: int) -> np.ndarray:
    finite = np.isfinite(values)
    count = finite.sum(axis=axis)
    return np.divide(
        np.where(finite, values, 0.0).sum(axis=axis),
        count,
        out=np.full(count.shape, np.nan, dtype=float),
        where=count > 0,
    )


class SectorFlowLeadershipCube(IntradayPathCube):
    """Add causal cross-sector flow, rotation, and leadership factors."""

    def factors(self, decision: int) -> dict[str, np.ndarray]:
        output = super().factors(decision)
        if "sector_signed_flow_breadth" in output:
            return output

        sector_indices = np.asarray(v12.SECTORS, dtype=int)
        returns = self.bar_return[:, : decision + 1, :][:, :, sector_indices]
        volumes = self.bar_volume[:, : decision + 1, :][:, :, sector_indices]
        closes = self.closes[:, : decision + 1, :][:, :, sector_indices]

        signed_notional = np.sign(returns) * volumes * closes
        signed_flow = np.nansum(signed_notional, axis=1)
        absolute_flow = np.nansum(np.abs(signed_notional), axis=1)
        flow_imbalance = np.divide(
            signed_flow,
            absolute_flow,
            out=np.full_like(signed_flow, np.nan),
            where=absolute_flow > 0,
        )
        current_return = output["current_return"][:, sector_indices]
        path_efficiency = output["path_efficiency"][:, sector_indices]

        flow_breadth = _safe_mean(flow_imbalance > 0.0, axis=1)
        return_flow_agreement = _safe_mean(
            np.sign(current_return) == np.sign(flow_imbalance), axis=1
        )
        path_breadth = _safe_mean(path_efficiency, axis=1)
        flow_mean = _safe_mean(flow_imbalance, axis=1)
        flow_dispersion = np.sqrt(
            _safe_mean((flow_imbalance - flow_mean[:, None]) ** 2, axis=1)
        )

        split = max(2, decision // 2)
        early = np.nansum(returns[:, :split, :], axis=1)
        recent = np.nansum(returns[:, split:, :], axis=1)
        breadth_acceleration = _safe_mean(recent > 0.0, axis=1) - _safe_mean(
            early > 0.0, axis=1
        )
        early_volatility = np.sqrt(np.nansum(returns[:, :split, :] ** 2, axis=1))
        recent_volatility = np.sqrt(np.nansum(returns[:, split:, :] ** 2, axis=1))
        volatility_ratio = np.divide(
            recent_volatility,
            early_volatility,
            out=np.full_like(recent_volatility, np.nan),
            where=early_volatility > 0,
        )
        volatility_contraction = _safe_mean(volatility_ratio, axis=1)

        sorted_return = np.sort(current_return, axis=1)
        leadership_spread = _safe_mean(sorted_return[:, -3:], axis=1) - _safe_mean(
            sorted_return[:, :3], axis=1
        )
        return_abs_sum = np.nansum(np.abs(current_return), axis=1)
        finite_return = np.isfinite(current_return)
        maximum_absolute_return = np.where(
            finite_return.any(axis=1),
            np.where(finite_return, np.abs(current_return), -np.inf).max(axis=1),
            np.nan,
        )
        leadership_concentration = np.divide(
            maximum_absolute_return,
            return_abs_sum,
            out=np.full(len(current_return), np.nan),
            where=return_abs_sum > 0,
        )

        # Sector order is XLB, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY, XLC.
        growth_local = np.asarray((4, 9, 10), dtype=int)
        defensive_local = np.asarray((5, 7, 8), dtype=int)
        growth_minus_defensive_return = _safe_mean(
            current_return[:, growth_local], axis=1
        ) - _safe_mean(current_return[:, defensive_local], axis=1)
        growth_minus_defensive_flow = _safe_mean(
            flow_imbalance[:, growth_local], axis=1
        ) - _safe_mean(flow_imbalance[:, defensive_local], axis=1)

        daily = {
            "sector_signed_flow_breadth": flow_breadth,
            "sector_return_flow_agreement": return_flow_agreement,
            "sector_path_efficiency_breadth": path_breadth,
            "sector_flow_dispersion": flow_dispersion,
            "sector_breadth_acceleration": breadth_acceleration,
            "sector_volatility_contraction": volatility_contraction,
            "sector_leadership_spread": leadership_spread,
            "sector_leadership_concentration": leadership_concentration,
            "growth_minus_defensive_return": growth_minus_defensive_return,
            "growth_minus_defensive_flow": growth_minus_defensive_flow,
        }
        for name, values in daily.items():
            output[name] = np.repeat(values[:, None], len(v12.SYMBOLS), axis=1)
        return output


def specifications() -> list[tuple[str, float, float]]:
    return [
        (family, quantile, alpha)
        for family in FACTOR_SETS
        for quantile in QUANTILES
        for alpha in ALPHAS
    ]


def main() -> None:
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.GATE_DECISION = GATE_DECISION
    campaign.MODERN_ENTRY = MODERN_ENTRY
    campaign.QUANTILES = QUANTILES
    campaign.ALPHAS = ALPHAS
    campaign.FACTOR_SETS = FACTOR_SETS
    campaign.IntradayPathCube = SectorFlowLeadershipCube
    campaign.main()


if __name__ == "__main__":
    main()
