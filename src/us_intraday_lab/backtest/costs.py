"""Versioned execution-cost assumptions.

The v1 values are conservative research-model inputs approved on 2026-07-27.
They are not representations of current broker or regulatory fee schedules and
must be calibrated against paper fills before live use.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Final, cast


def _exact_finite_number(value: object, *, name: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be an exact int or float")
    normalized = float(cast("int | float", value))
    if not isfinite(normalized):
        raise ValueError(f"{name} must be finite")
    return normalized


@dataclass(frozen=True)
class CostModel:
    """One-way variable execution-cost assumptions."""

    model_id: str
    half_spread_bps: float
    slippage_bps: float
    commission_per_share_usd: float

    def __post_init__(self) -> None:
        components = {
            "half_spread_bps": self.half_spread_bps,
            "slippage_bps": self.slippage_bps,
            "commission_per_share_usd": self.commission_per_share_usd,
        }
        normalized = {
            name: _exact_finite_number(value, name=name) for name, value in components.items()
        }
        if any(component < 0 for component in normalized.values()):
            raise ValueError("cost components must be finite and non-negative")
        object.__setattr__(
            self,
            "half_spread_bps",
            normalized["half_spread_bps"],
        )
        object.__setattr__(self, "slippage_bps", normalized["slippage_bps"])
        object.__setattr__(
            self,
            "commission_per_share_usd",
            normalized["commission_per_share_usd"],
        )
        if not self.model_id:
            raise ValueError("model_id must be non-empty")

    @property
    def price_impact_bps(self) -> float:
        """Adverse half-spread plus slippage applied to a reference price."""

        return self.half_spread_bps + self.slippage_bps

    def variable_cost(self, notional_usd: float, quantity: int) -> float:
        """Return one-way modeled cost for positive notional and integer shares."""

        normalized_notional = _exact_finite_number(notional_usd, name="notional_usd")
        if normalized_notional <= 0:
            raise ValueError("notional_usd must be finite and positive")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        price_cost = normalized_notional * self.price_impact_bps / 10_000
        return price_cost + quantity * self.commission_per_share_usd

    def scaled(self, multiplier: float) -> "CostModel":
        """Scale every variable component for a sensitivity evaluation."""

        normalized_multiplier = _exact_finite_number(multiplier, name="multiplier")
        if normalized_multiplier <= 0:
            raise ValueError("multiplier must be finite and positive")
        return CostModel(
            model_id=f"{self.model_id}-x{normalized_multiplier:g}",
            half_spread_bps=self.half_spread_bps * normalized_multiplier,
            slippage_bps=self.slippage_bps * normalized_multiplier,
            commission_per_share_usd=(self.commission_per_share_usd * normalized_multiplier),
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
