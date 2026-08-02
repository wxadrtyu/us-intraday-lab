"""Transparent, monotonic ranking for candidates that passed every hard gate."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import cast

from us_intraday_lab.validation.gates import HardGateEvaluation

COMPONENT_WEIGHTS: Mapping[str, float] = MappingProxyType(
    {
        "return_consistency": 0.30,
        "drawdown_quality": 0.20,
        "profit_factor_quality": 0.20,
        "walk_forward_consistency": 0.20,
        "cost_resilience": 0.10,
    }
)
RETURN_NORMALIZATION_SCALE = 0.10
DRAWDOWN_NORMALIZATION_LIMIT = 0.08


def _identity(value: object, *, name: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{name} must be a non-empty exact string")
    return value


def _finite(value: object, *, name: str) -> float:
    if type(value) not in {int, float}:
        raise TypeError(f"{name} must be an exact finite number")
    numeric = cast("int | float", value)
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be finite")
    return float(numeric)


def _bounded(value: object, *, name: str) -> float:
    normalized = _finite(value, name=name)
    if not 0.0 <= normalized <= 1.0:
        raise ValueError(f"{name} must be between 0 and 1")
    return normalized


@dataclass(frozen=True, slots=True)
class RankingEvidence:
    """Validation and final-test quality retained for an already gated candidate.

    Cost sensitivity is the fraction of base net return lost under the 1.5x
    cost scenario. Zero means no loss; one means the base return was fully lost.
    """

    strategy_id: str
    strategy_content_sha256: str
    gate_evaluation: HardGateEvaluation
    validation_net_return: float
    final_test_net_return: float
    validation_max_drawdown: float
    final_test_max_drawdown: float
    validation_profit_factor: float
    final_test_profit_factor: float
    profitable_walk_forward_fraction: float
    validation_cost_sensitivity: float
    final_test_cost_sensitivity: float

    def __post_init__(self) -> None:
        _identity(self.strategy_id, name="strategy_id")
        _sha256(self.strategy_content_sha256, name="strategy_content_sha256")
        if type(self.gate_evaluation) is not HardGateEvaluation:
            raise TypeError("gate_evaluation must be an exact HardGateEvaluation")
        gate_evaluation = HardGateEvaluation(
            strategy_id=self.gate_evaluation.strategy_id,
            split_id=self.gate_evaluation.split_id,
            gate_results=self.gate_evaluation.gate_results,
            passed=self.gate_evaluation.passed,
            failure_reason_codes=self.gate_evaluation.failure_reason_codes,
        )
        object.__setattr__(self, "gate_evaluation", gate_evaluation)
        for name in ("validation_net_return", "final_test_net_return"):
            value = _finite(getattr(self, name), name=name)
            if value <= 0.0:
                raise ValueError(f"{name} must be positive for ranked survivors")
            object.__setattr__(self, name, value)
        for name in ("validation_max_drawdown", "final_test_max_drawdown"):
            object.__setattr__(self, name, _bounded(getattr(self, name), name=name))
        for name in ("validation_profit_factor", "final_test_profit_factor"):
            value = _finite(getattr(self, name), name=name)
            if value < 1.0:
                raise ValueError(f"{name} must be at least 1")
            object.__setattr__(self, name, value)
        for name in (
            "profitable_walk_forward_fraction",
            "validation_cost_sensitivity",
            "final_test_cost_sensitivity",
        ):
            object.__setattr__(self, name, _bounded(getattr(self, name), name=name))


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    strategy_id: str
    strategy_content_sha256: str
    score: float
    normalized_components: Mapping[str, float]
    component_weights: Mapping[str, float]

    def __post_init__(self) -> None:
        _identity(self.strategy_id, name="strategy_id")
        _sha256(self.strategy_content_sha256, name="strategy_content_sha256")
        score = _bounded(self.score, name="score")
        components = _validated_component_mapping(
            self.normalized_components,
            name="normalized_components",
        )
        weights = _validated_component_mapping(
            self.component_weights,
            name="component_weights",
        )
        if set(components) != set(COMPONENT_WEIGHTS) or weights != COMPONENT_WEIGHTS:
            raise ValueError("ranking components and weights must use the published formula")
        derived = math.fsum(components[name] * weights[name] for name in COMPONENT_WEIGHTS)
        if not math.isclose(score, derived, rel_tol=0.0, abs_tol=1e-15):
            raise ValueError("score must equal the transparent weighted components")
        object.__setattr__(self, "score", score)
        object.__setattr__(self, "normalized_components", MappingProxyType(components))
        object.__setattr__(self, "component_weights", MappingProxyType(weights))


def _sha256(value: object, *, name: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{name} must be a lowercase sha256")
    return value


def _validated_component_mapping(value: object, *, name: str) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be a mapping")
    if any(type(key) is not str for key in value):
        raise TypeError(f"{name} keys must be exact strings")
    return {key: _bounded(component, name=f"{name}[{key}]") for key, component in value.items()}


def _return_quality(value: float) -> float:
    """Map positive returns smoothly to [0, 1) without peer-relative scaling."""

    return value / (RETURN_NORMALIZATION_SCALE + value)


def _harmonic_mean(first: float, second: float) -> float:
    return 2.0 * first * second / (first + second)


def _profit_factor_quality(value: float) -> float:
    """Map profit factor 1..infinity monotonically to 0..1."""

    return (value - 1.0) / value


def _components(evidence: RankingEvidence) -> dict[str, float]:
    validation_return = _return_quality(evidence.validation_net_return)
    final_return = _return_quality(evidence.final_test_net_return)
    return {
        "return_consistency": _harmonic_mean(validation_return, final_return),
        "drawdown_quality": 1.0
        - min(
            max(evidence.validation_max_drawdown, evidence.final_test_max_drawdown)
            / DRAWDOWN_NORMALIZATION_LIMIT,
            1.0,
        ),
        "profit_factor_quality": (
            _profit_factor_quality(evidence.validation_profit_factor)
            + _profit_factor_quality(evidence.final_test_profit_factor)
        )
        / 2.0,
        "walk_forward_consistency": evidence.profitable_walk_forward_fraction,
        "cost_resilience": 1.0
        - max(evidence.validation_cost_sensitivity, evidence.final_test_cost_sensitivity),
    }


def _revalidate(value: RankingEvidence) -> RankingEvidence:
    if type(value) is not RankingEvidence:
        raise TypeError("ranking inputs must be exact RankingEvidence values")
    return RankingEvidence(**{field: getattr(value, field) for field in value.__slots__})


def rank_survivors(candidates: tuple[RankingEvidence, ...]) -> tuple[RankedCandidate, ...]:
    """Rank only all-gate survivors; reject mixed or failed input batches."""

    if type(candidates) is not tuple:
        raise TypeError("candidates must be an exact tuple")
    validated = tuple(_revalidate(item) for item in candidates)
    if len({item.strategy_id for item in validated}) != len(validated):
        raise ValueError("ranked strategy_id values must be unique")
    ranked: list[RankedCandidate] = []
    for item in validated:
        if item.gate_evaluation.strategy_id != item.strategy_id:
            raise ValueError("ranking strategy_id must match gate evaluation strategy_id")
        if not item.gate_evaluation.passed:
            raise ValueError("candidates with failed hard gates cannot be ranked")
        components = _components(item)
        score = math.fsum(components[name] * COMPONENT_WEIGHTS[name] for name in COMPONENT_WEIGHTS)
        ranked.append(
            RankedCandidate(
                strategy_id=item.strategy_id,
                strategy_content_sha256=item.strategy_content_sha256,
                score=score,
                normalized_components=components,
                component_weights=COMPONENT_WEIGHTS,
            )
        )
    return tuple(
        sorted(
            ranked,
            key=lambda item: (-item.score, item.strategy_content_sha256),
        )
    )
