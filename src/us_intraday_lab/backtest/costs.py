"""Versioned execution-cost assumptions.

The v1 values are conservative research-model inputs approved on 2026-07-27.
They are not representations of current broker or regulatory fee schedules and
must be calibrated against paper fills before live use.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Final


@dataclass(frozen=True)
class CostModel:
    """One-way variable execution-cost assumptions."""

    model_id: str
    half_spread_bps: float
    slippage_bps: float
    commission_per_share_usd: float

    def __post_init__(self) -> None:
        components = (
            self.half_spread_bps,
            self.slippage_bps,
            self.commission_per_share_usd,
        )
        if not self.model_id:
            raise ValueError("model_id must be non-empty")
        if not all(isfinite(component) and component >= 0 for component in components):
            raise ValueError("cost components must be finite and non-negative")

    @property
    def price_impact_bps(self) -> float:
        """Adverse half-spread plus slippage applied to a reference price."""

        return self.half_spread_bps + self.slippage_bps

    def variable_cost(self, notional_usd: float, quantity: int) -> float:
        """Return one-way modeled cost for positive notional and integer shares."""

        if not isfinite(notional_usd) or notional_usd <= 0:
            raise ValueError("notional_usd must be finite and positive")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        price_cost = notional_usd * self.price_impact_bps / 10_000
        return price_cost + quantity * self.commission_per_share_usd

    def scaled(self, multiplier: float) -> "CostModel":
        """Scale every variable component for a sensitivity evaluation."""

        if not isfinite(multiplier) or multiplier <= 0:
            raise ValueError("multiplier must be finite and positive")
        return CostModel(
            model_id=f"{self.model_id}-x{multiplier:g}",
            half_spread_bps=self.half_spread_bps * multiplier,
            slippage_bps=self.slippage_bps * multiplier,
            commission_per_share_usd=self.commission_per_share_usd * multiplier,
        )


# Approved Task 4 v1 assumptions (2026-07-27), pending paper-fill calibration.
_SCENARIOS: Final[dict[str, CostModel]] = {
    "optimistic": CostModel(
        model_id="cost-optimistic-1.0.0",
        half_spread_bps=0.5,
        slippage_bps=0.5,
        commission_per_share_usd=0.0,
    ),
    "base": CostModel(
        model_id="cost-base-1.0.0",
        half_spread_bps=1.0,
        slippage_bps=2.0,
        commission_per_share_usd=0.0,
    ),
    "stress": CostModel(
        model_id="cost-stress-1.0.0",
        half_spread_bps=2.0,
        slippage_bps=5.0,
        commission_per_share_usd=0.0,
    ),
}

COST_SCENARIOS: Final[Mapping[str, CostModel]] = MappingProxyType(_SCENARIOS)
