from us_intraday_lab.long_horizon.gates import (
    LongHorizonGateEvidence,
    evaluate_long_horizon_gates,
)
from us_intraday_lab.validation.gates import CandidateGateEvidence


def _missing_old_evidence() -> CandidateGateEvidence:
    return CandidateGateEvidence(
        strategy_id="strategy-a",
        split_id="split-a",
        source_refs=("backtest:a",),
        base_net_return=-0.01,
        cost_1_5x_net_return=None,
        closed_trades=None,
        max_drawdown=None,
        profit_factor=None,
        walk_forward_results=None,
        parameter_neighborhood=None,
        symbol_concentration=None,
        start_date_stability=None,
        null_test=None,
        required_symbols=("AAPL", "QQQ"),
    )


def test_new_gates_do_not_replace_existing_gate_failures() -> None:
    result = evaluate_long_horizon_gates(
        LongHorizonGateEvidence(
            historical=_missing_old_evidence(),
            oos_sessions=120,
            cost_adjusted_annualized_return=0.15,
            information_ratio=0.8,
        )
    )

    assert "NONPOSITIVE_BASE_RETURN" in result.failure_reason_codes
    assert result.gate_results[-3].reason_code == "INSUFFICIENT_OOS_SESSIONS"
    assert result.gate_results[-2].reason_code == "COST_ADJUSTED_ANNUALIZED_RETURN_TOO_LOW"
    assert result.gate_results[-1].reason_code == "OOS_INFORMATION_RATIO_TOO_LOW"
    assert all(gate.passed for gate in result.gate_results[-3:])


def test_each_long_horizon_floor_is_inclusive_and_fail_complete() -> None:
    result = evaluate_long_horizon_gates(
        LongHorizonGateEvidence(
            historical=_missing_old_evidence(),
            oos_sessions=89,
            cost_adjusted_annualized_return=0.099,
            information_ratio=0.49,
        )
    )

    assert result.failure_reason_codes[-3:] == (
        "INSUFFICIENT_OOS_SESSIONS",
        "COST_ADJUSTED_ANNUALIZED_RETURN_TOO_LOW",
        "OOS_INFORMATION_RATIO_TOO_LOW",
    )

