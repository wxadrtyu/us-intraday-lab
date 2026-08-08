from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from us_intraday_lab.long_horizon.final_ledger import FinalTestIsolationError
from us_intraday_lab.long_horizon.orchestrator import (
    PhaseEvaluation,
    finalize_long_horizon_campaign,
    screen_long_horizon_campaign,
)
from us_intraday_lab.long_horizon.proposal import LongHorizonHypothesisProposal


def _proposal(proposal_id: str, seed: int) -> LongHorizonHypothesisProposal:
    return LongHorizonHypothesisProposal.model_validate(
        {
            "proposal_id": proposal_id,
            "schema_version": "1.0.0",
            "entry_template": "momentum_5m",
            "symbols": ["AAPL", "QQQ"],
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
            0.001 + edge + ((index % 3) - 1) * 0.00001
            for index, _session in enumerate(sessions)
        )
        return PhaseEvaluation(
            strategy_id=strategy.strategy_id,
            sessions=sessions,
            base_session_returns=returns,
            stress_session_returns=tuple(value - 0.0001 for value in returns),
            closed_trades=max(100, len(sessions)),
            max_drawdown=0.02,
            profit_factor=1.4,
            pnl_by_symbol={"AAPL": 55.0, "QQQ": 45.0},
        )

    def benchmark_returns(self, sessions: tuple[date, ...]) -> tuple[float, ...]:
        return tuple(0.0002 for _ in sessions)


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
