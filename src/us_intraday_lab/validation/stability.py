"""Deterministic robustness gates over precomputed candidate evidence."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

PRODUCTION_SYMBOLS = ("SPY", "QQQ", "IWM")
AAPL_QQQ_SYMBOLS = ("AAPL", "QQQ")
SPY_IWM_SYMBOLS = ("SPY", "IWM")
SPY_TQQQ_SYMBOLS = ("SPY", "TQQQ")
TQQQ_UPRO_SYMBOLS = ("TQQQ", "UPRO")
TQQQ_SOXL_SYMBOLS = ("TQQQ", "SOXL")
LONG_HORIZON_SYMBOLS = frozenset(
    (
        *AAPL_QQQ_SYMBOLS,
        *SPY_IWM_SYMBOLS,
        *SPY_TQQQ_SYMBOLS,
        *TQQQ_UPRO_SYMBOLS,
        *TQQQ_SOXL_SYMBOLS,
    )
)
ALLOWED_SYMBOL_SCOPES = (
    PRODUCTION_SYMBOLS,
    AAPL_QQQ_SYMBOLS,
    SPY_IWM_SYMBOLS,
    SPY_TQQQ_SYMBOLS,
    TQQQ_UPRO_SYMBOLS,
    TQQQ_SOXL_SYMBOLS,
)


def _finite_number(value: object, *, name: str) -> float:
    if type(value) not in {int, float}:
        raise ValueError(f"{name} must be an exact finite number")
    numeric = cast("int | float", value)
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be an exact finite number")
    return float(numeric)


def _fraction(value: object, *, name: str, require_majority: bool = False) -> float:
    normalized = _finite_number(value, name=name)
    lower = 0.5 if require_majority else 0.0
    if not lower < normalized <= 1.0:
        qualifier = "greater than 0.5 and" if require_majority else "greater than 0 and"
        raise ValueError(f"{name} must be {qualifier} at most 1")
    return normalized


@dataclass(frozen=True, slots=True)
class PerturbationObservation:
    """One traceable, base-cost result for a configured perturbation."""

    observation_id: str
    net_return: float
    max_drawdown: float

    def __post_init__(self) -> None:
        if type(self.observation_id) is not str or not self.observation_id:
            raise ValueError("observation_id must be a non-empty string")
        net_return = _finite_number(self.net_return, name="net_return")
        max_drawdown = _finite_number(self.max_drawdown, name="max_drawdown")
        if not 0.0 <= max_drawdown <= 1.0:
            raise ValueError("max_drawdown must be between 0 and 1")
        object.__setattr__(self, "net_return", net_return)
        object.__setattr__(self, "max_drawdown", max_drawdown)


def _exact_string_tuple(value: object, *, name: str, minimum: int) -> tuple[str, ...]:
    if type(value) is not tuple:
        raise TypeError(f"{name} must be an exact tuple")
    if len(value) < minimum:
        raise ValueError(f"{name} must contain at least {minimum} items")
    if any(type(item) is not str or not item for item in value):
        raise ValueError(f"{name} must contain non-empty exact strings")
    if len(set(value)) != len(value):
        raise ValueError(f"{name} must be unique")
    return value


@dataclass(frozen=True, slots=True)
class ParameterNeighborhoodConfig:
    baseline_id: str
    neighbor_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.baseline_id) is not str or not self.baseline_id:
            raise ValueError("baseline_id must be a non-empty exact string")
        neighbors = _exact_string_tuple(
            self.neighbor_ids,
            name="neighbor_ids",
            minimum=2,
        )
        if self.baseline_id in neighbors:
            raise ValueError("baseline_id must not be included in neighbor_ids")


@dataclass(frozen=True, slots=True)
class StartDateObservation:
    """One result tied to an exact configured session offset."""

    offset_sessions: int
    net_return: float
    max_drawdown: float

    def __post_init__(self) -> None:
        if type(self.offset_sessions) is not int:
            raise TypeError("offset_sessions must be an exact integer")
        net_return = _finite_number(self.net_return, name="net_return")
        max_drawdown = _finite_number(self.max_drawdown, name="max_drawdown")
        if not 0.0 <= max_drawdown <= 1.0:
            raise ValueError("max_drawdown must be between 0 and 1")
        object.__setattr__(self, "net_return", net_return)
        object.__setattr__(self, "max_drawdown", max_drawdown)


@dataclass(frozen=True, slots=True)
class StartDateConfig:
    offsets: tuple[int, ...]

    def __post_init__(self) -> None:
        if type(self.offsets) is not tuple:
            raise TypeError("offsets must be an exact tuple")
        if len(self.offsets) < 2:
            raise ValueError("offsets must contain at least 2 items")
        if any(type(offset) is not int for offset in self.offsets):
            raise TypeError("offsets must contain exact integers")
        if tuple(sorted(self.offsets)) != self.offsets or len(set(self.offsets)) != len(
            self.offsets
        ):
            raise ValueError("offsets must be sorted and unique")


RobustnessObservation = PerturbationObservation | StartDateObservation


@dataclass(frozen=True, slots=True)
class StabilityAssessment:
    passed: bool
    reason_code: str
    profitable_count: int
    required_profitable_fraction: float
    max_drawdown: float
    observations: tuple[RobustnessObservation, ...]
    parameter_config: ParameterNeighborhoodConfig | None
    start_date_config: StartDateConfig | None


@dataclass(frozen=True, slots=True)
class SymbolConcentrationAssessment:
    passed: bool
    reason_code: str
    total_profit: float
    positive_profit: float
    max_positive_profit_share: float
    profit_by_symbol: Mapping[str, float]
    positive_profit_share_by_symbol: Mapping[str, float]


def _observations(value: object) -> tuple[PerturbationObservation, ...]:
    if type(value) is not tuple or not value:
        raise TypeError("observations must be a non-empty exact tuple")
    if len(value) < 2:
        raise ValueError("parameter neighborhoods require at least 2 adjacent observations")
    if any(type(item) is not PerturbationObservation for item in value):
        raise TypeError("observations must contain exact PerturbationObservation values")
    reparsed = tuple(
        PerturbationObservation(
            observation_id=item.observation_id,
            net_return=item.net_return,
            max_drawdown=item.max_drawdown,
        )
        for item in value
    )
    observation_ids = tuple(item.observation_id for item in reparsed)
    if len(set(observation_ids)) != len(observation_ids):
        raise ValueError("observations must exactly match declared neighbor IDs")
    return reparsed


def _start_date_observations(value: object) -> tuple[StartDateObservation, ...]:
    if type(value) is not tuple or not value:
        raise TypeError("observations must be a non-empty exact tuple")
    if len(value) < 2:
        raise ValueError("start-date sensitivity requires at least 2 offsets")
    if any(type(item) is not StartDateObservation for item in value):
        raise TypeError("observations must contain exact StartDateObservation values")
    reparsed = tuple(
        StartDateObservation(
            offset_sessions=item.offset_sessions,
            net_return=item.net_return,
            max_drawdown=item.max_drawdown,
        )
        for item in value
    )
    return reparsed


def _assess_perturbations(
    observations: tuple[RobustnessObservation, ...],
    *,
    required_profitable_fraction: object,
    max_drawdown: object,
    pass_reason: str,
    fail_reason: str,
    parameter_config: ParameterNeighborhoodConfig | None,
    start_date_config: StartDateConfig | None,
) -> StabilityAssessment:
    required = _fraction(
        required_profitable_fraction,
        name="required_profitable_fraction",
        require_majority=True,
    )
    drawdown_gate = _finite_number(max_drawdown, name="max_drawdown")
    if not 0.0 <= drawdown_gate <= 1.0:
        raise ValueError("max_drawdown must be between 0 and 1")
    profitable_count = sum(item.net_return > 0.0 for item in observations)
    profitable_fraction = profitable_count / len(observations)
    passed = profitable_fraction >= required and all(
        item.max_drawdown <= drawdown_gate for item in observations
    )
    return StabilityAssessment(
        passed=passed,
        reason_code=pass_reason if passed else fail_reason,
        profitable_count=profitable_count,
        required_profitable_fraction=required,
        max_drawdown=drawdown_gate,
        observations=observations,
        parameter_config=parameter_config,
        start_date_config=start_date_config,
    )


def assess_parameter_neighborhood(
    observations: tuple[PerturbationObservation, ...],
    *,
    config: ParameterNeighborhoodConfig,
    required_profitable_fraction: float = 0.6,
    max_drawdown: float = 0.08,
) -> StabilityAssessment:
    """Require a profitable plateau with no neighbor above the drawdown gate."""

    if type(config) is not ParameterNeighborhoodConfig:
        raise TypeError("config must be an exact ParameterNeighborhoodConfig")
    validated_config = ParameterNeighborhoodConfig(
        baseline_id=config.baseline_id,
        neighbor_ids=config.neighbor_ids,
    )
    evidence = _observations(observations)
    if tuple(item.observation_id for item in evidence) != validated_config.neighbor_ids:
        raise ValueError("observations must exactly match declared neighbor IDs")
    return _assess_perturbations(
        evidence,
        required_profitable_fraction=required_profitable_fraction,
        max_drawdown=max_drawdown,
        pass_reason="STABLE_PARAMETER_NEIGHBORHOOD",
        fail_reason="UNSTABLE_PARAMETER_NEIGHBORHOOD",
        parameter_config=validated_config,
        start_date_config=None,
    )


def assess_start_date_sensitivity(
    observations: tuple[StartDateObservation, ...],
    *,
    config: StartDateConfig,
    required_profitable_fraction: float = 0.6,
    max_drawdown: float = 0.08,
) -> StabilityAssessment:
    """Require a profitable majority and retain every configured offset result."""

    if type(config) is not StartDateConfig:
        raise TypeError("config must be an exact StartDateConfig")
    validated_config = StartDateConfig(offsets=config.offsets)
    evidence = _start_date_observations(observations)
    if tuple(item.offset_sessions for item in evidence) != validated_config.offsets:
        raise ValueError("observations must exactly match configured offsets")
    return _assess_perturbations(
        evidence,
        required_profitable_fraction=required_profitable_fraction,
        max_drawdown=max_drawdown,
        pass_reason="STABLE_START_DATE",
        fail_reason="START_DATE_INSTABILITY",
        parameter_config=None,
        start_date_config=validated_config,
    )


def assess_symbol_concentration(
    profit_by_symbol: Mapping[str, float],
    *,
    required_symbols: tuple[str, ...] = PRODUCTION_SYMBOLS,
    max_positive_profit_share: float = 0.70,
) -> SymbolConcentrationAssessment:
    """Assess concentration against positive profit while retaining losses."""

    if not isinstance(profit_by_symbol, Mapping):
        raise TypeError("profit_by_symbol must be a mapping")
    if required_symbols not in ALLOWED_SYMBOL_SCOPES:
        raise ValueError("required_symbols must use an approved exact scope")
    if set(profit_by_symbol) != set(required_symbols) or len(profit_by_symbol) != len(
        required_symbols
    ):
        raise ValueError("profit_by_symbol must contain exactly the required symbol scope")
    normalized = {
        symbol: _finite_number(profit_by_symbol[symbol], name=f"profit_by_symbol[{symbol}]")
        for symbol in required_symbols
    }
    share_gate = _fraction(max_positive_profit_share, name="max_positive_profit_share")
    total_profit = math.fsum(normalized.values())
    positive_profit = math.fsum(max(value, 0.0) for value in normalized.values())
    shares = {
        symbol: max(value, 0.0) / positive_profit if positive_profit > 0.0 else 0.0
        for symbol, value in normalized.items()
    }
    passed = total_profit > 0.0 and all(share <= share_gate for share in shares.values())
    return SymbolConcentrationAssessment(
        passed=passed,
        reason_code="DIVERSIFIED_SYMBOL_PROFIT" if passed else "SYMBOL_PROFIT_CONCENTRATION",
        total_profit=total_profit,
        positive_profit=positive_profit,
        max_positive_profit_share=share_gate,
        profit_by_symbol=MappingProxyType(normalized),
        positive_profit_share_by_symbol=MappingProxyType(shares),
    )
