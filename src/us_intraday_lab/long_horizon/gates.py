from __future__ import annotations

import math
from dataclasses import dataclass

from us_intraday_lab.contracts.validation import GateEvidence, GateResult
from us_intraday_lab.validation.gates import (
    HARD_GATE_REASON_CODES,
    CandidateGateEvidence,
    evaluate_hard_gates,
)

MIN_OOS_SESSIONS = 90
MIN_COST_ADJUSTED_ANNUALIZED_RETURN = 0.10
MIN_OOS_INFORMATION_RATIO = 0.50
LONG_HORIZON_GATE_REASON_CODES = (
    *HARD_GATE_REASON_CODES,
    "INSUFFICIENT_OOS_SESSIONS",
    "COST_ADJUSTED_ANNUALIZED_RETURN_TOO_LOW",
    "OOS_INFORMATION_RATIO_TOO_LOW",
)


@dataclass(frozen=True, slots=True)
class LongHorizonGateEvidence:
    historical: CandidateGateEvidence
    oos_sessions: int
    cost_adjusted_annualized_return: float
    information_ratio: float

    def __post_init__(self) -> None:
        if type(self.historical) is not CandidateGateEvidence:
            raise TypeError("historical must be exact CandidateGateEvidence")
        if type(self.oos_sessions) is not int or self.oos_sessions < 0:
            raise ValueError("oos_sessions must be a non-negative integer")
        for field in ("cost_adjusted_annualized_return", "information_ratio"):
            value = getattr(self, field)
            if type(value) not in {int, float} or not math.isfinite(value):
                raise ValueError(f"{field} must be finite")
            object.__setattr__(self, field, float(value))


@dataclass(frozen=True, slots=True)
class LongHorizonGateEvaluation:
    strategy_id: str
    split_id: str
    gate_results: tuple[GateResult, ...]
    passed: bool
    failure_reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        observed = tuple(result.reason_code for result in self.gate_results)
        if observed != LONG_HORIZON_GATE_REASON_CODES:
            raise ValueError("long-horizon gates must retain fixed additive order")
        failures = tuple(result.reason_code for result in self.gate_results if not result.passed)
        if self.failure_reason_codes != failures or self.passed != (not failures):
            raise ValueError("long-horizon gate status must match every result")


def _gate(
    candidate: CandidateGateEvidence,
    *,
    reason_code: str,
    metric_name: str,
    threshold: float,
    observed: float,
    passed: bool,
) -> GateResult:
    return GateResult(
        reason_code=reason_code,
        threshold=threshold,
        observed=observed,
        passed=passed,
        evidence=GateEvidence(
            evidence_id=f"{candidate.strategy_id}:{candidate.split_id}:{reason_code}",
            metric_name=metric_name,
            source_refs=candidate.source_refs,
            values={"observed": float(observed), "threshold": float(threshold)},
        ),
    )


def evaluate_long_horizon_gates(
    evidence: LongHorizonGateEvidence,
) -> LongHorizonGateEvaluation:
    """Preserve all historical gates and append the three long-horizon floors."""

    if type(evidence) is not LongHorizonGateEvidence:
        raise TypeError("evidence must be exact LongHorizonGateEvidence")
    historical = evaluate_hard_gates(evidence.historical)
    appended = (
        _gate(
            evidence.historical,
            reason_code="INSUFFICIENT_OOS_SESSIONS",
            metric_name="oos_sessions",
            threshold=float(MIN_OOS_SESSIONS),
            observed=float(evidence.oos_sessions),
            passed=evidence.oos_sessions >= MIN_OOS_SESSIONS,
        ),
        _gate(
            evidence.historical,
            reason_code="COST_ADJUSTED_ANNUALIZED_RETURN_TOO_LOW",
            metric_name="cost_adjusted_annualized_return",
            threshold=MIN_COST_ADJUSTED_ANNUALIZED_RETURN,
            observed=evidence.cost_adjusted_annualized_return,
            passed=(
                evidence.cost_adjusted_annualized_return
                >= MIN_COST_ADJUSTED_ANNUALIZED_RETURN
            ),
        ),
        _gate(
            evidence.historical,
            reason_code="OOS_INFORMATION_RATIO_TOO_LOW",
            metric_name="information_ratio",
            threshold=MIN_OOS_INFORMATION_RATIO,
            observed=evidence.information_ratio,
            passed=evidence.information_ratio >= MIN_OOS_INFORMATION_RATIO,
        ),
    )
    results = (*historical.gate_results, *appended)
    failures = tuple(result.reason_code for result in results if not result.passed)
    return LongHorizonGateEvaluation(
        strategy_id=historical.strategy_id,
        split_id=historical.split_id,
        gate_results=results,
        passed=not failures,
        failure_reason_codes=failures,
    )
