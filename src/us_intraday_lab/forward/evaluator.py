"""Hard-gate-first forward evaluation orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from us_intraday_lab.contracts.registry import RegistryState
from us_intraday_lab.forward.eligibility import (
    EligibilityDecision,
    ForwardEvidence,
    evaluate_eligibility,
)
from us_intraday_lab.forward.lifecycle import promote_ranked
from us_intraday_lab.forward.ranking import RankingResult, rank_eligible
from us_intraday_lab.registry.store import RegistryStore


@dataclass(frozen=True, slots=True)
class EvaluationInput:
    evidence: ForwardEvidence
    lifecycle_state: RegistryState
    ranked_capacity_available: bool = True


@dataclass(frozen=True, slots=True)
class ForwardEvaluation:
    decisions: tuple[EligibilityDecision, ...]
    rankings: tuple[RankingResult, ...]


def evaluate_forward(inputs: tuple[EvaluationInput, ...]) -> ForwardEvaluation:
    """Run all hard gates first and pass only eligible evidence into ranking."""

    decisions = tuple(
        evaluate_eligibility(
            item.evidence,
            lifecycle_state=item.lifecycle_state,
            capacity_available=item.ranked_capacity_available,
        )
        for item in inputs
    )
    eligible_ids = {decision.strategy_id for decision in decisions if decision.eligible}
    rankings = rank_eligible(
        tuple(item.evidence for item in inputs if item.evidence.strategy_id in eligible_ids)
    )
    return ForwardEvaluation(decisions=decisions, rankings=rankings)


def evaluate_and_promote(
    store: RegistryStore,
    inputs: tuple[EvaluationInput, ...],
    *,
    occurred_at: datetime,
) -> ForwardEvaluation:
    """Evaluate, rank, then transactionally apply evidence-linked promotions."""

    evaluation = evaluate_forward(inputs)
    for result in evaluation.rankings:
        promote_ranked(store, result, occurred_at=occurred_at)
    return evaluation
