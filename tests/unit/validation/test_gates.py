from dataclasses import replace
from datetime import date

import pytest

from us_intraday_lab.contracts.validation import WalkForwardWindowResult
from us_intraday_lab.validation.gates import (
    CandidateGateEvidence,
    evaluate_hard_gates,
)
from us_intraday_lab.validation.null_tests import (
    HoldingRuleScoringConfig,
    NullDistribution,
    NullSequenceScore,
    NullTestResult,
)
from us_intraday_lab.validation.stability import (
    ParameterNeighborhoodConfig,
    PerturbationObservation,
    StartDateConfig,
    StartDateObservation,
    assess_parameter_neighborhood,
    assess_start_date_sensitivity,
    assess_symbol_concentration,
)


def _walk_forward(
    net_returns: tuple[float, ...] = (0.02, 0.01, 0.03, -0.01, 0.02),
) -> tuple[WalkForwardWindowResult, ...]:
    return tuple(
        WalkForwardWindowResult(
            window_id=f"wf-{index}",
            strategy_id="strategy-a",
            train_start=date(2025, 1, 1),
            train_end=date(2025, 1, 31),
            validation_start=date(2025, 2, 1),
            validation_end=date(2025, 2, 28),
            metrics_by_cost_scenario={"base": {"net_return": net_return}},
        )
        for index, net_return in enumerate(net_returns)
    )


def _parameter_assessment(*, passed: bool = True):
    returns = (0.02, 0.01, 0.03) if passed else (0.02, -0.01, -0.02)
    observations = tuple(
        PerturbationObservation(f"neighbor-{index}", net_return, 0.04)
        for index, net_return in enumerate(returns)
    )
    return assess_parameter_neighborhood(
        observations,
        config=ParameterNeighborhoodConfig(
            baseline_id="baseline",
            neighbor_ids=tuple(item.observation_id for item in observations),
        ),
    )


def _start_date_assessment(*, passed: bool = True):
    returns = (0.02, 0.01, 0.03) if passed else (0.02, -0.01, -0.02)
    offsets = (-5, 0, 5)
    return assess_start_date_sensitivity(
        tuple(
            StartDateObservation(offset, net_return, 0.04)
            for offset, net_return in zip(offsets, returns, strict=True)
        ),
        config=StartDateConfig(offsets=offsets),
    )


def _null_result(*, passed: bool = True) -> NullTestResult:
    observed = 10.0 if passed else 1.0
    return NullTestResult(
        passed=passed,
        reason_code="PASSED_NULL_TEST" if passed else "NULL_TEST_FAILED",
        observed_score=NullSequenceScore(observed, 120, 0),
        seed=7,
        repetitions=200,
        percentile=0.95,
        evidence_sha256="a" * 64,
        evidence_opportunity_ids=("opportunity-1",),
        scoring_config=HoldingRuleScoringConfig("score", "v1", "cost-v1"),
        framework_operation_bound=1_000,
        distributions=(
            NullDistribution(
                method="SESSION_SIGNAL_PERMUTATION",
                statistics=(1.0,) * 200,
                accepted_entry_counts=(120,) * 200,
                rejected_entry_counts=(0,) * 200,
                percentile_threshold=1.0,
            ),
            NullDistribution(
                method="SESSION_SAFE_TIMESTAMP_SHIFT",
                statistics=(1.0,) * 200,
                accepted_entry_counts=(120,) * 200,
                rejected_entry_counts=(0,) * 200,
                percentile_threshold=1.0,
            ),
        ),
        trade_count_by_symbol_session={
            "2025-02-03:SPY": 40,
            "2025-02-03:QQQ": 40,
            "2025-02-03:IWM": 40,
        },
    )


def passing_evidence() -> CandidateGateEvidence:
    return CandidateGateEvidence(
        strategy_id="strategy-a",
        split_id="split-a",
        source_refs=("backtest:a", "robustness:a"),
        base_net_return=0.05,
        cost_1_5x_net_return=0.02,
        closed_trades=120,
        max_drawdown=0.06,
        profit_factor=1.30,
        walk_forward_results=_walk_forward(),
        parameter_neighborhood=_parameter_assessment(),
        symbol_concentration=assess_symbol_concentration({"SPY": 40.0, "QQQ": 35.0, "IWM": 25.0}),
        start_date_stability=_start_date_assessment(),
        null_test=_null_result(),
    )


EXPECTED_ORDER = (
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


def test_passing_candidate_returns_all_gates_in_fixed_order() -> None:
    result = evaluate_hard_gates(passing_evidence())

    assert result.passed is True
    assert result.failure_reason_codes == ()
    assert tuple(gate.reason_code for gate in result.gate_results) == EXPECTED_ORDER
    assert all(gate.passed for gate in result.gate_results)


def test_inclusive_gate_boundaries_pass_and_returns_remain_strictly_positive() -> None:
    evidence = replace(
        passing_evidence(),
        base_net_return=1e-12,
        cost_1_5x_net_return=1e-12,
        closed_trades=100,
        max_drawdown=0.08,
        profit_factor=1.15,
        walk_forward_results=_walk_forward((0.01, 0.01, 0.01, -0.01, -0.01)),
        symbol_concentration=assess_symbol_concentration({"SPY": 70, "QQQ": 20, "IWM": 10}),
    )

    assert evaluate_hard_gates(evidence).passed is True


@pytest.mark.parametrize(
    ("changes", "reason_code"),
    [
        ({"base_net_return": 0.0}, "NONPOSITIVE_BASE_RETURN"),
        ({"cost_1_5x_net_return": 0.0}, "NONPOSITIVE_COST_1_5X_RETURN"),
        ({"closed_trades": 99}, "INSUFFICIENT_TRADES"),
        ({"max_drawdown": 0.080001}, "MAX_DRAWDOWN_EXCEEDED"),
        ({"profit_factor": 1.1499}, "PROFIT_FACTOR_TOO_LOW"),
        (
            {"walk_forward_results": _walk_forward((0.02, 0.01, -0.01, -0.02, -0.03))},
            "INSUFFICIENT_PROFITABLE_WF_WINDOWS",
        ),
        (
            {"parameter_neighborhood": _parameter_assessment(passed=False)},
            "UNSTABLE_PARAMETER_NEIGHBORHOOD",
        ),
        (
            {
                "symbol_concentration": assess_symbol_concentration(
                    {"SPY": 80, "QQQ": 10, "IWM": 10}
                )
            },
            "SYMBOL_PROFIT_CONCENTRATION",
        ),
        (
            {"start_date_stability": _start_date_assessment(passed=False)},
            "START_DATE_INSTABILITY",
        ),
        ({"null_test": _null_result(passed=False)}, "NULL_TEST_FAILED"),
    ],
)
def test_each_hard_gate_has_stable_failure_code(
    changes: dict[str, object], reason_code: str
) -> None:
    result = evaluate_hard_gates(replace(passing_evidence(), **changes))

    assert result.passed is False
    assert result.failure_reason_codes == (reason_code,)


def test_gate_evaluation_is_fail_complete() -> None:
    evidence = replace(
        passing_evidence(),
        base_net_return=-0.01,
        cost_1_5x_net_return=None,
        closed_trades=1,
        max_drawdown=0.50,
        profit_factor=None,
        walk_forward_results=None,
        parameter_neighborhood=None,
        symbol_concentration=None,
        start_date_stability=None,
        null_test=None,
    )

    result = evaluate_hard_gates(evidence)

    assert result.failure_reason_codes == EXPECTED_ORDER
    assert tuple(gate.observed for gate in result.gate_results[1:])[:1] == ("MISSING",)


def test_walk_forward_evidence_must_belong_to_candidate() -> None:
    forged = _walk_forward()[0].model_copy(update={"strategy_id": "other"})
    evidence = replace(passing_evidence(), walk_forward_results=(forged, *_walk_forward()[1:]))

    with pytest.raises(ValueError, match="strategy_id"):
        evaluate_hard_gates(evidence)


def test_gate_thresholds_are_fixed_instead_of_trusting_weaker_upstream_assessments() -> None:
    observations = tuple(
        PerturbationObservation(f"neighbor-{index}", net_return, 0.04)
        for index, net_return in enumerate(
            (0.01, 0.01, 0.01, 0.01, 0.01, -0.01, -0.01, -0.01, -0.01)
        )
    )
    weak_assessment = assess_parameter_neighborhood(
        observations,
        config=ParameterNeighborhoodConfig(
            baseline_id="baseline",
            neighbor_ids=tuple(item.observation_id for item in observations),
        ),
        required_profitable_fraction=0.51,
    )
    result = evaluate_hard_gates(
        replace(passing_evidence(), parameter_neighborhood=weak_assessment)
    )

    assert weak_assessment.passed is True
    assert result.failure_reason_codes == ("UNSTABLE_PARAMETER_NEIGHBORHOOD",)

    weak_symbol_assessment = assess_symbol_concentration(
        {"SPY": 75, "QQQ": 15, "IWM": 10},
        max_positive_profit_share=0.80,
    )
    symbol_result = evaluate_hard_gates(
        replace(passing_evidence(), symbol_concentration=weak_symbol_assessment)
    )

    assert weak_symbol_assessment.passed is True
    assert symbol_result.failure_reason_codes == ("SYMBOL_PROFIT_CONCENTRATION",)
