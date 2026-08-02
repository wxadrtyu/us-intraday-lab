from dataclasses import replace

import pytest

from us_intraday_lab.contracts.validation import GateEvidence, GateResult
from us_intraday_lab.validation.gates import (
    HARD_GATE_REASON_CODES,
    HardGateEvaluation,
)
from us_intraday_lab.validation.ranking import RankingEvidence, rank_survivors


def _gate_evaluation(strategy_id: str, *, passed: bool = True) -> HardGateEvaluation:
    gate_results = tuple(
        GateResult(
            reason_code=reason_code,
            threshold="PASSED",
            observed="PASSED" if passed or index else "FAILED",
            passed=passed or index > 0,
            evidence=GateEvidence(
                evidence_id=f"{strategy_id}:{reason_code}",
                metric_name=reason_code.lower(),
                source_refs=("validation:test",),
                values={},
            ),
        )
        for index, reason_code in enumerate(HARD_GATE_REASON_CODES)
    )
    failures = tuple(item.reason_code for item in gate_results if not item.passed)
    return HardGateEvaluation(
        strategy_id=strategy_id,
        split_id="split-a",
        gate_results=gate_results,
        passed=not failures,
        failure_reason_codes=failures,
    )


def ranking_evidence(
    *, strategy_id: str = "strategy-a", content_hash: str = "a" * 64
) -> RankingEvidence:
    return RankingEvidence(
        strategy_id=strategy_id,
        strategy_content_sha256=content_hash,
        gate_evaluation=_gate_evaluation(strategy_id),
        validation_net_return=0.06,
        final_test_net_return=0.05,
        validation_max_drawdown=0.05,
        final_test_max_drawdown=0.06,
        validation_profit_factor=1.30,
        final_test_profit_factor=1.25,
        profitable_walk_forward_fraction=0.80,
        validation_cost_sensitivity=0.20,
        final_test_cost_sensitivity=0.25,
    )


def _score(evidence: RankingEvidence) -> float:
    return rank_survivors((evidence,))[0].score


def test_ranking_stores_every_transparent_normalized_component() -> None:
    ranked = rank_survivors((ranking_evidence(),))[0]

    assert set(ranked.normalized_components) == {
        "return_consistency",
        "drawdown_quality",
        "profit_factor_quality",
        "walk_forward_consistency",
        "cost_resilience",
    }
    assert all(0.0 <= value <= 1.0 for value in ranked.normalized_components.values())
    assert ranked.score == pytest.approx(
        sum(
            ranked.normalized_components[name] * ranked.component_weights[name]
            for name in ranked.normalized_components
        )
    )


@pytest.mark.parametrize(
    ("field", "improved"),
    [
        ("validation_net_return", 0.07),
        ("final_test_net_return", 0.06),
        ("validation_profit_factor", 1.40),
        ("final_test_profit_factor", 1.35),
        ("profitable_walk_forward_fraction", 1.0),
    ],
)
def test_improved_return_consistency_or_profit_factor_cannot_lower_score(
    field: str, improved: float
) -> None:
    baseline = ranking_evidence()
    assert _score(replace(baseline, **{field: improved})) >= _score(baseline)


@pytest.mark.parametrize(
    ("field", "worse"),
    [
        ("validation_max_drawdown", 0.07),
        ("final_test_max_drawdown", 0.075),
        ("validation_cost_sensitivity", 0.40),
        ("final_test_cost_sensitivity", 0.40),
    ],
)
def test_increased_drawdown_or_cost_sensitivity_cannot_raise_score(
    field: str, worse: float
) -> None:
    baseline = ranking_evidence()
    assert _score(replace(baseline, **{field: worse})) <= _score(baseline)


def test_ties_resolve_by_strategy_content_hash() -> None:
    later = ranking_evidence(strategy_id="later", content_hash="f" * 64)
    earlier = ranking_evidence(strategy_id="earlier", content_hash="0" * 64)

    ranked = rank_survivors((later, earlier))

    assert tuple(item.strategy_id for item in ranked) == ("earlier", "later")


def test_failed_candidate_is_never_ranked() -> None:
    failed = replace(
        ranking_evidence(),
        gate_evaluation=_gate_evaluation("strategy-a", passed=False),
    )

    with pytest.raises(ValueError, match="failed hard gates"):
        rank_survivors((failed,))


def test_ranking_rejects_mismatched_or_malformed_identity() -> None:
    with pytest.raises(ValueError, match="strategy_id"):
        rank_survivors((replace(ranking_evidence(), strategy_id="other"),))
    with pytest.raises(ValueError, match="sha256"):
        replace(ranking_evidence(), strategy_content_sha256="not-a-hash")


def test_ranking_revalidates_frozen_gate_evaluation() -> None:
    evidence = ranking_evidence()
    object.__setattr__(evidence.gate_evaluation, "passed", False)

    with pytest.raises(ValueError, match="passed"):
        rank_survivors((evidence,))
