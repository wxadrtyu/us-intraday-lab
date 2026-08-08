"""Fail-complete hard gates for strategy-factory candidates."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from us_intraday_lab.contracts.validation import GateEvidence, GateResult, WalkForwardWindowResult
from us_intraday_lab.validation.null_tests import NullTestResult
from us_intraday_lab.validation.stability import (
    ALLOWED_SYMBOL_SCOPES,
    PRODUCTION_SYMBOLS,
    PerturbationObservation,
    StabilityAssessment,
    StartDateObservation,
    SymbolConcentrationAssessment,
    assess_parameter_neighborhood,
    assess_start_date_sensitivity,
    assess_symbol_concentration,
)

MIN_CLOSED_TRADES = 100
MAX_DRAWDOWN = 0.08
MIN_PROFIT_FACTOR = 1.15
MIN_PROFITABLE_WF_FRACTION = 0.60
MAX_SYMBOL_POSITIVE_PROFIT_SHARE = 0.70

HARD_GATE_REASON_CODES = (
    "NONPOSITIVE_BASE_RETURN",
    "NONPOSITIVE_COST_1_5X_RETURN",
    "INSUFFICIENT_TRADES",
    "MAX_DRAWDOWN_EXCEEDED",
    "PROFIT_FACTOR_TOO_LOW",
    "INSUFFICIENT_PROFITABLE_WF_WINDOWS",
    "UNSTABLE_PARAMETER_NEIGHBORHOOD",
    "SYMBOL_PROFIT_CONCENTRATION",
    "START_DATE_INSTABILITY",
    "NULL_TEST_FAILED",
)


def _optional_number(value: object, *, name: str) -> float | None:
    if value is None:
        return None
    if type(value) not in {int, float}:
        raise TypeError(f"{name} must be an exact finite number or None")
    numeric = cast("int | float", value)
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be finite")
    return float(numeric)


def _optional_nonnegative_int(value: object, *, name: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise TypeError(f"{name} must be an exact integer or None")
    if value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _strict_identity(value: object, *, name: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{name} must be a non-empty exact string")
    return value


@dataclass(frozen=True, slots=True)
class CandidateGateEvidence:
    """All evidence needed to evaluate every approved hard gate once."""

    strategy_id: str
    split_id: str
    source_refs: tuple[str, ...]
    base_net_return: float | None
    cost_1_5x_net_return: float | None
    closed_trades: int | None
    max_drawdown: float | None
    profit_factor: float | None
    walk_forward_results: tuple[WalkForwardWindowResult, ...] | None
    parameter_neighborhood: StabilityAssessment | None
    symbol_concentration: SymbolConcentrationAssessment | None
    start_date_stability: StabilityAssessment | None
    null_test: NullTestResult | None
    required_symbols: tuple[str, ...] = PRODUCTION_SYMBOLS

    def __post_init__(self) -> None:
        _strict_identity(self.strategy_id, name="strategy_id")
        _strict_identity(self.split_id, name="split_id")
        if type(self.source_refs) is not tuple or not self.source_refs:
            raise TypeError("source_refs must be a non-empty exact tuple")
        if any(type(item) is not str or not item for item in self.source_refs):
            raise ValueError("source_refs must contain non-empty exact strings")
        for name in (
            "base_net_return",
            "cost_1_5x_net_return",
            "max_drawdown",
            "profit_factor",
        ):
            object.__setattr__(self, name, _optional_number(getattr(self, name), name=name))
        if self.max_drawdown is not None and not 0.0 <= self.max_drawdown <= 1.0:
            raise ValueError("max_drawdown must be between 0 and 1")
        object.__setattr__(
            self,
            "closed_trades",
            _optional_nonnegative_int(self.closed_trades, name="closed_trades"),
        )
        if self.walk_forward_results is not None and type(self.walk_forward_results) is not tuple:
            raise TypeError("walk_forward_results must be an exact tuple or None")
        if self.required_symbols not in ALLOWED_SYMBOL_SCOPES:
            raise ValueError("required_symbols must use an approved exact scope")


@dataclass(frozen=True, slots=True)
class HardGateEvaluation:
    strategy_id: str
    split_id: str
    gate_results: tuple[GateResult, ...]
    passed: bool
    failure_reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        _strict_identity(self.strategy_id, name="strategy_id")
        _strict_identity(self.split_id, name="split_id")
        if type(self.gate_results) is not tuple or len(self.gate_results) != len(
            HARD_GATE_REASON_CODES
        ):
            raise ValueError("gate_results must contain every hard gate")
        reparsed = tuple(GateResult.model_validate(item.model_dump()) for item in self.gate_results)
        observed_codes = tuple(item.reason_code for item in reparsed)
        if observed_codes != HARD_GATE_REASON_CODES:
            raise ValueError("gate_results must use fixed hard-gate order")
        failures = tuple(item.reason_code for item in reparsed if not item.passed)
        if type(self.passed) is not bool or self.passed != (not failures):
            raise ValueError("passed must agree with every hard gate")
        if self.failure_reason_codes != failures:
            raise ValueError("failure_reason_codes must exactly match failed gates")
        object.__setattr__(self, "gate_results", reparsed)


def _gate(
    evidence: CandidateGateEvidence,
    *,
    reason_code: str,
    metric_name: str,
    threshold: float | str,
    observed: float | str,
    passed: bool,
    values: Mapping[str, float],
) -> GateResult:
    retained_values = {
        key: float(value)
        for key, value in values.items()
        if type(key) is str and key and type(value) in {int, float} and math.isfinite(value)
    }
    if len(retained_values) != len(values):
        raise ValueError("gate evidence values must be named finite numbers")
    return GateResult(
        reason_code=reason_code,
        threshold=threshold,
        observed=observed,
        passed=passed,
        evidence=GateEvidence(
            evidence_id=f"{evidence.strategy_id}:{evidence.split_id}:{reason_code}",
            metric_name=metric_name,
            source_refs=evidence.source_refs,
            values=retained_values,
        ),
    )


def _observed(value: float | None) -> float | str:
    return "MISSING" if value is None else value


def _validated_walk_forward(
    value: tuple[WalkForwardWindowResult, ...] | None,
    *,
    strategy_id: str,
) -> tuple[WalkForwardWindowResult, ...] | None:
    if value is None:
        return None
    if not value:
        return None
    reparsed = tuple(WalkForwardWindowResult.model_validate(item.model_dump()) for item in value)
    if any(item.strategy_id != strategy_id for item in reparsed):
        raise ValueError("walk-forward strategy_id must match candidate strategy_id")
    if len({item.window_id for item in reparsed}) != len(reparsed):
        raise ValueError("walk-forward window_id values must be unique")
    return reparsed


def _validated_parameter(value: StabilityAssessment | None) -> StabilityAssessment | None:
    if value is None:
        return None
    if type(value) is not StabilityAssessment or value.parameter_config is None:
        raise TypeError("parameter_neighborhood must be a parameter StabilityAssessment")
    return assess_parameter_neighborhood(
        cast("tuple[PerturbationObservation, ...]", value.observations),
        config=value.parameter_config,
    )


def _validated_start_date(value: StabilityAssessment | None) -> StabilityAssessment | None:
    if value is None:
        return None
    if type(value) is not StabilityAssessment or value.start_date_config is None:
        raise TypeError("start_date_stability must be a start-date StabilityAssessment")
    return assess_start_date_sensitivity(
        cast("tuple[StartDateObservation, ...]", value.observations),
        config=value.start_date_config,
    )


def _validated_symbol(
    value: SymbolConcentrationAssessment | None,
    *,
    required_symbols: tuple[str, ...],
) -> SymbolConcentrationAssessment | None:
    if value is None:
        return None
    if type(value) is not SymbolConcentrationAssessment:
        raise TypeError("symbol_concentration must be a SymbolConcentrationAssessment")
    return assess_symbol_concentration(
        value.profit_by_symbol,
        required_symbols=required_symbols,
        max_positive_profit_share=MAX_SYMBOL_POSITIVE_PROFIT_SHARE,
    )


def _validated_null(
    value: NullTestResult | None,
    *,
    required_symbols: tuple[str, ...],
) -> NullTestResult | None:
    if value is None:
        return None
    if type(value) is not NullTestResult:
        raise TypeError("null_test must be a NullTestResult")
    if type(value.passed) is not bool:
        raise TypeError("null_test passed must be an exact bool")
    if value.reason_code != ("PASSED_NULL_TEST" if value.passed else "NULL_TEST_FAILED"):
        raise ValueError("null_test reason_code must agree with passed")
    if len(value.evidence_sha256) != 64 or any(
        character not in "0123456789abcdef" for character in value.evidence_sha256
    ):
        raise ValueError("null_test evidence_sha256 must be lowercase sha256")
    methods = tuple(item.method for item in value.distributions)
    if methods != ("SESSION_SIGNAL_PERMUTATION", "SESSION_SAFE_TIMESTAMP_SHIFT"):
        raise ValueError("null_test must retain both approved null methods")
    if any(
        len(item.statistics) != value.repetitions
        or len(item.accepted_entry_counts) != value.repetitions
        or len(item.rejected_entry_counts) != value.repetitions
        for item in value.distributions
    ):
        raise ValueError("null_test distributions must match repetitions")
    derived_passed = all(
        value.observed_profit > item.percentile_threshold for item in value.distributions
    )
    if derived_passed != value.passed:
        raise ValueError("null_test passed must agree with retained distributions")
    covered_symbols = {
        symbol
        for key in value.trade_count_by_symbol_session
        for symbol in required_symbols
        if key.endswith(f":{symbol}")
    }
    if covered_symbols != set(required_symbols):
        raise ValueError("null_test evidence must cover the required symbol scope")
    return value


def evaluate_hard_gates(evidence: CandidateGateEvidence) -> HardGateEvaluation:
    """Evaluate every hard gate in fixed order without short-circuiting."""

    if type(evidence) is not CandidateGateEvidence:
        raise TypeError("evidence must be an exact CandidateGateEvidence")
    candidate = CandidateGateEvidence(
        **{field: getattr(evidence, field) for field in evidence.__slots__}
    )
    walk_forward = _validated_walk_forward(
        candidate.walk_forward_results,
        strategy_id=candidate.strategy_id,
    )
    parameter = _validated_parameter(candidate.parameter_neighborhood)
    symbol = _validated_symbol(
        candidate.symbol_concentration,
        required_symbols=candidate.required_symbols,
    )
    start_date = _validated_start_date(candidate.start_date_stability)
    null_test = _validated_null(candidate.null_test, required_symbols=candidate.required_symbols)

    wf_profitable = (
        sum(item.metrics_by_cost_scenario["base"]["net_return"] > 0.0 for item in walk_forward)
        if walk_forward
        else 0
    )
    wf_total = len(walk_forward) if walk_forward else 0
    wf_fraction = wf_profitable / wf_total if wf_total else None

    specs: tuple[tuple[str, str, float | str, float | None, bool, Mapping[str, float]], ...] = (
        (
            "NONPOSITIVE_BASE_RETURN",
            "base_net_return",
            "> 0",
            candidate.base_net_return,
            candidate.base_net_return is not None and candidate.base_net_return > 0.0,
            {},
        ),
        (
            "NONPOSITIVE_COST_1_5X_RETURN",
            "cost_1_5x_net_return",
            "> 0",
            candidate.cost_1_5x_net_return,
            candidate.cost_1_5x_net_return is not None and candidate.cost_1_5x_net_return > 0.0,
            {},
        ),
        (
            "INSUFFICIENT_TRADES",
            "closed_trades",
            MIN_CLOSED_TRADES,
            candidate.closed_trades,
            candidate.closed_trades is not None and candidate.closed_trades >= MIN_CLOSED_TRADES,
            {},
        ),
        (
            "MAX_DRAWDOWN_EXCEEDED",
            "max_drawdown",
            MAX_DRAWDOWN,
            candidate.max_drawdown,
            candidate.max_drawdown is not None and candidate.max_drawdown <= MAX_DRAWDOWN,
            {},
        ),
        (
            "PROFIT_FACTOR_TOO_LOW",
            "profit_factor",
            MIN_PROFIT_FACTOR,
            candidate.profit_factor,
            candidate.profit_factor is not None and candidate.profit_factor >= MIN_PROFIT_FACTOR,
            {},
        ),
        (
            "INSUFFICIENT_PROFITABLE_WF_WINDOWS",
            "profitable_walk_forward_fraction",
            MIN_PROFITABLE_WF_FRACTION,
            wf_fraction,
            wf_fraction is not None and wf_fraction >= MIN_PROFITABLE_WF_FRACTION,
            {"profitable_windows": wf_profitable, "total_windows": wf_total},
        ),
        (
            "UNSTABLE_PARAMETER_NEIGHBORHOOD",
            "parameter_neighborhood",
            "PASSED",
            None if parameter is None else int(parameter.passed),
            parameter is not None and parameter.passed,
            {},
        ),
        (
            "SYMBOL_PROFIT_CONCENTRATION",
            "largest_symbol_positive_profit_share",
            MAX_SYMBOL_POSITIVE_PROFIT_SHARE,
            None if symbol is None else max(symbol.positive_profit_share_by_symbol.values()),
            symbol is not None and symbol.passed,
            {},
        ),
        (
            "START_DATE_INSTABILITY",
            "start_date_stability",
            "PASSED",
            None if start_date is None else int(start_date.passed),
            start_date is not None and start_date.passed,
            {},
        ),
        (
            "NULL_TEST_FAILED",
            "null_test",
            "PASSED",
            None if null_test is None else int(null_test.passed),
            null_test is not None and null_test.passed,
            {},
        ),
    )
    results = tuple(
        _gate(
            candidate,
            reason_code=reason_code,
            metric_name=metric_name,
            threshold=threshold,
            observed=_observed(observed),
            passed=passed,
            values=values,
        )
        for reason_code, metric_name, threshold, observed, passed, values in specs
    )
    failures = tuple(result.reason_code for result in results if not result.passed)
    return HardGateEvaluation(
        strategy_id=candidate.strategy_id,
        split_id=candidate.split_id,
        gate_results=results,
        passed=not failures,
        failure_reason_codes=failures,
    )
