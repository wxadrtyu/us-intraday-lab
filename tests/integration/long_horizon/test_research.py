from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from us_intraday_lab.backtest.metrics import TradeRecord
from us_intraday_lab.long_horizon.final_ledger import FinalTestIsolationError
from us_intraday_lab.long_horizon.orchestrator import (
    NoLongHorizonCandidateError,
    PhaseEvaluation,
    cost_adjusted_trade_session_returns,
    finalize_long_horizon_campaign,
    matched_benchmark_session_returns,
    screen_long_horizon_campaign,
)
from us_intraday_lab.long_horizon.proposal import LongHorizonHypothesisProposal


def _proposal(
    proposal_id: str,
    seed: int,
    *,
    symbols: tuple[str, str] = ("AAPL", "QQQ"),
) -> LongHorizonHypothesisProposal:
    return LongHorizonHypothesisProposal.model_validate(
        {
            "proposal_id": proposal_id,
            "schema_version": "1.0.0",
            "entry_template": "momentum_5m",
            "symbols": list(symbols),
            "parameter_ranges": {
                "return_1_min": {"values": [0.0005, 0.001]},
                "stop_loss_bps": {"values": [40, 60]},
            },
            "max_variants": 4,
            "seed": seed,
            "rationale": "Causal fixture proposal for one-use campaign orchestration.",
            "provenance": "fixture",
        }
    )


class _Backend:
    def __init__(self) -> None:
        self.phases: list[str] = []
        self.sessions = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(300))

    def accepted_sessions(self, dataset_id: str) -> tuple[date, ...]:
        assert dataset_id == "data-a"
        return self.sessions

    def evaluate(self, strategy, sessions: tuple[date, ...], *, phase: str) -> PhaseEvaluation:
        self.phases.append(phase)
        edge = int(strategy.strategy_id[-1], 16) / 100_000
        returns = tuple(
            0.001 + edge + ((index % 3) - 1) * 0.00001 for index, _session in enumerate(sessions)
        )
        return PhaseEvaluation(
            strategy_id=strategy.strategy_id,
            sessions=sessions,
            base_session_returns=returns,
            stress_session_returns=tuple(value - 0.0001 for value in returns),
            cost_1_5x_session_returns=tuple(value - 0.00005 for value in returns),
            closed_trades=max(100, len(sessions)),
            max_drawdown=0.02,
            profit_factor=1.4,
            pnl_by_symbol={"AAPL": 55.0, "QQQ": 45.0},
        )

    def benchmark_returns(self, strategy, sessions: tuple[date, ...]) -> tuple[float, ...]:
        del strategy
        return tuple(0.0002 for _ in sessions)


class _MixedValidationBackend(_Backend):
    def __init__(self) -> None:
        super().__init__()
        self.validation_count = 0

    def evaluate(self, strategy, sessions: tuple[date, ...], *, phase: str) -> PhaseEvaluation:
        result = super().evaluate(strategy, sessions, phase=phase)
        if phase != "validation":
            return result
        daily_return = 0.00045 if self.validation_count == 0 else 0.00015
        self.validation_count += 1
        return PhaseEvaluation(
            strategy_id=result.strategy_id,
            sessions=result.sessions,
            base_session_returns=result.base_session_returns,
            stress_session_returns=result.stress_session_returns,
            cost_1_5x_session_returns=tuple(daily_return for _ in sessions),
            closed_trades=result.closed_trades,
            max_drawdown=result.max_drawdown,
            profit_factor=result.profit_factor,
            pnl_by_symbol=result.pnl_by_symbol,
        )


class _ConcentratedBackend(_Backend):
    def evaluate(self, strategy, sessions: tuple[date, ...], *, phase: str) -> PhaseEvaluation:
        result = super().evaluate(strategy, sessions, phase=phase)
        if phase != "validation":
            return result
        return PhaseEvaluation(
            strategy_id=result.strategy_id,
            sessions=result.sessions,
            base_session_returns=result.base_session_returns,
            stress_session_returns=result.stress_session_returns,
            cost_1_5x_session_returns=result.cost_1_5x_session_returns,
            closed_trades=result.closed_trades,
            max_drawdown=result.max_drawdown,
            profit_factor=result.profit_factor,
            pnl_by_symbol={"AAPL": 100.0, "QQQ": -1.0},
        )


class _SpyIwmBackend(_Backend):
    def evaluate(self, strategy, sessions: tuple[date, ...], *, phase: str) -> PhaseEvaluation:
        result = super().evaluate(strategy, sessions, phase=phase)
        return PhaseEvaluation(
            strategy_id=result.strategy_id,
            sessions=result.sessions,
            base_session_returns=result.base_session_returns,
            stress_session_returns=result.stress_session_returns,
            cost_1_5x_session_returns=result.cost_1_5x_session_returns,
            closed_trades=result.closed_trades,
            max_drawdown=result.max_drawdown,
            profit_factor=result.profit_factor,
            pnl_by_symbol={"SPY": 55.0, "IWM": 45.0},
        )


class _ScatteredValidationBackend(_Backend):
    def __init__(self) -> None:
        super().__init__()
        self.validation_counts: dict[str, int] = {}

    def evaluate(self, strategy, sessions: tuple[date, ...], *, phase: str) -> PhaseEvaluation:
        result = super().evaluate(strategy, sessions, phase=phase)
        if phase != "validation":
            return result
        proposal_id = strategy.strategy_id.rsplit("-", 1)[0]
        count = self.validation_counts.get(proposal_id, 0)
        self.validation_counts[proposal_id] = count + 1
        daily_return = 0.0005 if count == 0 else -0.0001
        return PhaseEvaluation(
            strategy_id=result.strategy_id,
            sessions=result.sessions,
            base_session_returns=tuple(daily_return for _ in sessions),
            stress_session_returns=tuple(daily_return - 0.00005 for _ in sessions),
            cost_1_5x_session_returns=tuple(daily_return - 0.00005 for _ in sessions),
            closed_trades=result.closed_trades,
            max_drawdown=result.max_drawdown,
            profit_factor=result.profit_factor,
            pnl_by_symbol=result.pnl_by_symbol,
        )


def test_screen_never_reads_or_reserves_final(tmp_path: Path) -> None:
    backend = _Backend()

    selection = screen_long_horizon_campaign(
        (_proposal("proposal-a", 1), _proposal("proposal-b", 2)),
        dataset_id="data-a",
        root=tmp_path,
        backend=backend,
    )

    assert selection.selection_manifest.is_file()
    assert selection.winner_id in selection.survivor_ids
    assert len(selection.survivor_ids) == 4
    assert "final_test" not in backend.phases
    assert not (tmp_path / "state" / "long_horizon_final.sqlite3").exists()


def test_screen_resumes_completed_phase_evaluations_from_checkpoints(
    tmp_path: Path,
) -> None:
    proposals = (_proposal("proposal-a", 1), _proposal("proposal-b", 2))
    first_backend = _Backend()
    first = screen_long_horizon_campaign(
        proposals,
        dataset_id="data-a",
        root=tmp_path,
        backend=first_backend,
    )
    assert first_backend.phases

    resumed_backend = _Backend()
    resumed = screen_long_horizon_campaign(
        proposals,
        dataset_id="data-a",
        root=tmp_path,
        backend=resumed_backend,
    )

    assert resumed_backend.phases == []
    assert resumed.selection_sha256 == first.selection_sha256


def test_screen_requires_ten_percent_winner_but_keeps_positive_neighbors(
    tmp_path: Path,
) -> None:
    backend = _MixedValidationBackend()

    selection = screen_long_horizon_campaign(
        (_proposal("proposal-a", 1), _proposal("proposal-b", 2)),
        dataset_id="data-a",
        root=tmp_path,
        backend=backend,
    )

    assert selection.winner_validation.cost_1_5x_annualized_return >= 0.10
    assert any(item.cost_1_5x_annualized_return < 0.10 for item in selection.validation_evaluations)


def test_screen_rejects_validation_profit_concentrated_in_one_symbol(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        NoLongHorizonCandidateError,
        match="fewer than four variants passed validation floors",
    ):
        screen_long_horizon_campaign(
            (_proposal("proposal-a", 1), _proposal("proposal-b", 2)),
            dataset_id="data-a",
            root=tmp_path,
            backend=_ConcentratedBackend(),
        )


def test_screen_accepts_the_closed_spy_iwm_scope(tmp_path: Path) -> None:
    selection = screen_long_horizon_campaign(
        (
            _proposal("proposal-spy-a", 1, symbols=("SPY", "IWM")),
            _proposal("proposal-spy-b", 2, symbols=("SPY", "IWM")),
        ),
        dataset_id="data-a",
        root=tmp_path,
        backend=_SpyIwmBackend(),
    )

    assert selection.winner_strategy.symbols == ("SPY", "IWM")


def test_screen_rejects_scattered_winners_without_one_four_variant_family(
    tmp_path: Path,
) -> None:
    proposals = tuple(_proposal(f"proposal-{index}", index) for index in range(4))

    with pytest.raises(
        NoLongHorizonCandidateError,
        match="fewer than four variants passed validation floors",
    ):
        screen_long_horizon_campaign(
            proposals,
            dataset_id="data-a",
            root=tmp_path,
            backend=_ScatteredValidationBackend(),
        )


def test_second_experiment_cannot_reopen_consumed_campaign_final(tmp_path: Path) -> None:
    backend = _Backend()
    selection = screen_long_horizon_campaign(
        (_proposal("proposal-a", 1), _proposal("proposal-b", 2)),
        dataset_id="data-a",
        root=tmp_path,
        backend=backend,
    )

    first = finalize_long_horizon_campaign(selection, root=tmp_path, backend=backend)

    assert first.final_consumed
    assert backend.phases.count("final_test") == 1
    with pytest.raises(FinalTestIsolationError, match="CAMPAIGN_FINAL_ALREADY_CONSUMED"):
        finalize_long_horizon_campaign(selection, root=tmp_path, backend=backend)
    assert backend.phases.count("final_test") == 1


def test_cost_adjustment_scales_recorded_cost_without_inventing_empty_day_pnl() -> None:
    first = date(2025, 1, 2)
    second = date(2025, 1, 3)
    trade = TradeRecord(
        symbol="AAPL",
        session=first,
        quantity=1,
        entry_time=datetime(2025, 1, 2, 15, tzinfo=UTC),
        exit_time=datetime(2025, 1, 2, 16, tzinfo=UTC),
        entry_price=100.0,
        exit_price=110.0,
        gross_pnl=10.0,
        net_pnl=8.0,
        cost_paid=2.0,
        forced=False,
    )

    returns = cost_adjusted_trade_session_returns(
        (trade,), (first, second), initial_cash=100.0, cost_multiplier=1.5
    )

    assert returns == pytest.approx((0.07, 0.0))


def test_matched_benchmark_uses_strategy_times_and_cash_notional() -> None:
    first = date(2025, 1, 2)
    second = date(2025, 1, 3)
    first_entry = datetime(2025, 1, 2, 15, tzinfo=UTC)
    first_exit = datetime(2025, 1, 2, 16, tzinfo=UTC)
    second_entry = datetime(2025, 1, 3, 15, tzinfo=UTC)
    second_exit = datetime(2025, 1, 3, 16, tzinfo=UTC)
    trades = (
        TradeRecord(
            symbol="TQQQ",
            session=first,
            quantity=5,
            entry_time=first_entry,
            exit_time=first_exit,
            entry_price=100.0,
            exit_price=101.0,
            gross_pnl=5.0,
            net_pnl=5.0,
            cost_paid=0.0,
            forced=False,
        ),
        TradeRecord(
            symbol="TQQQ",
            session=second,
            quantity=5,
            entry_time=second_entry,
            exit_time=second_exit,
            entry_price=100.0,
            exit_price=99.0,
            gross_pnl=-5.0,
            net_pnl=-5.0,
            cost_paid=0.0,
            forced=True,
        ),
    )
    bars = pd.DataFrame(
        [
            {"session_date": first, "available_at": first_entry, "open": 200.0, "close": 201.0},
            {"session_date": first, "available_at": first_exit, "open": 220.0, "close": 221.0},
            {"session_date": second, "available_at": second_entry, "open": 250.0, "close": 251.0},
            {"session_date": second, "available_at": second_exit, "open": 230.0, "close": 225.0},
        ]
    )

    returns = matched_benchmark_session_returns(
        trades,
        bars,
        (first, second),
        initial_cash=1_000.0,
    )

    assert returns == pytest.approx((0.05, -50.0 / 1_050.0))
