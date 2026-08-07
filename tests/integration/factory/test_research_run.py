import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from typing import Self

import pandas as pd
import pytest
from typer.testing import CliRunner

from us_intraday_lab.backtest.engine import BacktestEvent
from us_intraday_lab.backtest.metrics import TradeRecord
from us_intraday_lab.cli import app
from us_intraday_lab.factory import orchestrator as orchestrator_module
from us_intraday_lab.factory.orchestrator import (
    RESEARCH_STAGES,
    AcceptedResearchDataset,
    NullEvidenceSummary,
    PhaseEvidence,
    ResearchIntegrityError,
    RobustnessEvidence,
    RobustnessPoint,
    StartDatePoint,
    load_accepted_research_dataset,
    resume_research,
    run_research,
)
from us_intraday_lab.factory.proposal import FixtureProposalProvider
from us_intraday_lab.factory.variants import GeneratedVariant, generate_strategy_variants
from us_intraday_lab.registry.store import RegistryStore

PROPOSAL = Path(__file__).parents[2] / "fixtures" / "hypotheses" / "momentum_pullback.json"
ACCEPTED_AT = datetime(2026, 8, 2, 2, 0, tzinfo=UTC)
RUNNER = CliRunner()


def test_research_dataset_uses_only_sessions_shared_by_all_production_symbols(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from us_intraday_lab.data import catalog as catalog_module
    from us_intraday_lab.data import snapshot as snapshot_module

    sessions = tuple(date(2026, 4, day) for day in range(13, 23))
    executed: list[str] = []

    class FakeResult:
        def fetchall(self) -> list[tuple[date]]:
            return [(session,) for session in sessions]

    class FakeConnection:
        def execute(self, query: str) -> FakeResult:
            executed.append(query)
            return FakeResult()

        def __enter__(self) -> Self:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(catalog_module, "accept_dataset", lambda *args, **kwargs: None)
    monkeypatch.setattr(catalog_module, "connect_catalog", lambda **kwargs: FakeConnection())
    monkeypatch.setattr(
        snapshot_module,
        "verify_snapshot",
        lambda *args, **kwargs: SimpleNamespace(
            dataset_id="dataset",
            content_sha256="a" * 64,
            calendar_name="XNYS",
            calendar_version="test",
            created_at=ACCEPTED_AT,
        ),
    )

    dataset = load_accepted_research_dataset(root=tmp_path, dataset_id="dataset")

    assert dataset.sessions == sessions
    assert "HAVING COUNT(DISTINCT symbol) = 3" in executed[0]


class SyntheticAcceptedBackend:
    def __init__(self) -> None:
        self.phase_calls: list[tuple[str, str]] = []
        self.robustness_calls: list[str] = []

    def run_phase(
        self,
        *,
        variant: GeneratedVariant,
        phase: str,
        sessions: tuple[date, ...],
        experiment_id: str,
    ) -> PhaseEvidence:
        self.phase_calls.append((phase, variant.variant_id))
        good = variant.selection_reason == "baseline"
        net_return = 0.08 if good else -0.01
        if phase == "train":
            net_return += 0.01
        if phase == "final_test":
            net_return = 0.06
        scenario_metrics = {
            "optimistic": {
                "net_return": net_return + 0.01,
                "max_drawdown": 0.035 if good else 0.12,
                "profit_factor": 1.50 if good else 0.80,
                "trade_count": 125.0 if good else 30.0,
            },
            "base": {
                "net_return": net_return,
                "max_drawdown": 0.04 if good else 0.12,
                "profit_factor": 1.40 if good else 0.80,
                "trade_count": 120.0 if good else 30.0,
            },
            "stress": {
                "net_return": net_return - 0.02,
                "max_drawdown": 0.05 if good else 0.14,
                "profit_factor": 1.25 if good else 0.70,
                "trade_count": 118.0 if good else 28.0,
            },
        }
        return PhaseEvidence(
            strategy_id=variant.variant_id,
            phase=phase,
            job_id=f"job-{phase}-{variant.variant_id}",
            run_id=f"run-{phase}-{variant.variant_id}",
            result_sha256=("a" if good else "b") * 64,
            metrics_by_cost_scenario=scenario_metrics,
            cost_1_5x_net_return=net_return - 0.01,
            profit_by_symbol={
                "SPY": 40.0 if good else -5.0,
                "QQQ": 35.0 if good else -3.0,
                "IWM": 25.0 if good else -2.0,
            },
            session_net_returns={
                session.isoformat(): net_return / len(sessions) for session in sessions
            },
            source_refs=(f"{experiment_id}:{phase}:{variant.variant_id}",),
        )

    def robustness_evidence(
        self,
        *,
        variant: GeneratedVariant,
        validation_results: tuple[PhaseEvidence, ...],
        experiment_id: str,
    ) -> RobustnessEvidence:
        del validation_results
        self.robustness_calls.append(variant.variant_id)
        good = variant.selection_reason == "baseline"
        positive = (0.03, 0.02, 0.04) if good else (-0.02, -0.01, 0.01)
        return RobustnessEvidence(
            strategy_id=variant.variant_id,
            walk_forward_net_returns=(0.02, 0.01, 0.03, 0.01, -0.005)
            if good
            else (-0.02, -0.01, 0.01, -0.03, -0.01),
            parameter_points=tuple(
                RobustnessPoint(
                    observation_id=f"neighbor-{index}",
                    net_return=value,
                    max_drawdown=0.05 if good else 0.12,
                )
                for index, value in enumerate(positive)
            ),
            start_date_points=tuple(
                StartDatePoint(
                    offset_sessions=offset,
                    net_return=value,
                    max_drawdown=0.05 if good else 0.12,
                )
                for offset, value in zip((-5, 0, 5), positive, strict=True)
            ),
            null_evidence=NullEvidenceSummary(
                passed=good,
                seed=7,
                repetitions=200,
                percentile=0.95,
                observed_profit=100.0 if good else 1.0,
                permutation_threshold=20.0 if good else 2.0,
                timestamp_shift_threshold=25.0 if good else 2.0,
                evidence_sha256=("c" if good else "d") * 64,
                evidence_opportunity_ids=(f"null-{variant.variant_id}",),
                trade_count_by_symbol_session={
                    "2026-06-01:SPY": 40,
                    "2026-06-01:QQQ": 40,
                    "2026-06-01:IWM": 40,
                },
                permutation_statistics=((20.0 if good else 2.0),) * 200,
                permutation_accepted_entry_counts=(120,) * 200,
                permutation_rejected_entry_counts=(0,) * 200,
                timestamp_shift_statistics=((25.0 if good else 2.0),) * 200,
                timestamp_shift_accepted_entry_counts=(120,) * 200,
                timestamp_shift_rejected_entry_counts=(0,) * 200,
            ),
            source_refs=(f"{experiment_id}:robustness:{variant.variant_id}",),
        )


def _dataset() -> AcceptedResearchDataset:
    first = date(2026, 5, 1)
    sessions = tuple(first + timedelta(days=index) for index in range(20))
    return AcceptedResearchDataset(
        dataset_id="accepted-synthetic-v1",
        content_sha256="1" * 64,
        calendar_name="XNYS",
        calendar_version="test-calendar-1.0.0",
        sessions=sessions,
        accepted_at=ACCEPTED_AT,
    )


def test_complete_research_run_is_gated_auditable_and_idempotent(tmp_path: Path) -> None:
    root = tmp_path / "lab"
    root.mkdir()
    backend = SyntheticAcceptedBackend()
    proposal = FixtureProposalProvider(PROPOSAL).load()

    first = run_research(
        proposal=proposal,
        dataset=_dataset(),
        backend=backend,
        root=root,
        code_revision="a1b2c3d",
    )

    assert first.completed_stages == RESEARCH_STAGES
    assert first.variant_count == proposal.max_variants
    assert (
        len([call for call in backend.phase_calls if call[0] == "train"]) == proposal.max_variants
    )
    assert (
        len([call for call in backend.phase_calls if call[0] == "validation"])
        == proposal.max_variants
    )
    assert (
        tuple(strategy_id for phase, strategy_id in backend.phase_calls if phase == "final_test")
        == first.final_test_strategy_ids
    )
    assert len(first.final_test_strategy_ids) == 1
    assert first.survivor_ids == first.final_test_strategy_ids
    assert all(count == 10 for count in first.gate_result_counts.values())
    assert first.rejected_count == proposal.max_variants - 1

    registry = RegistryStore(first.registry_path)
    assert registry.get_current_state(first.survivor_ids[0]) == "paper_shadow"
    rejected_id = next(
        strategy_id
        for strategy_id in first.gate_result_counts
        if strategy_id not in first.survivor_ids
    )
    assert registry.get_current_state(rejected_id) == "rejected"
    assert registry.get_strategy_definition(rejected_id) is not None

    report = first.report_path.read_text(encoding="utf-8")
    assert "# 策略研究报告" in report
    assert proposal.thesis in report
    assert "硬门槛" in report
    assert "随机基准" in report
    assert "标的收益贡献" in report
    assert "开始日期稳定性" in report
    assert first.experiment_id in report
    assert _dataset().dataset_id in report
    assert "历史表现不代表未来收益" in report

    phase_call_count = len(backend.phase_calls)
    robustness_call_count = len(backend.robustness_calls)
    repeated = run_research(
        proposal=proposal,
        dataset=_dataset(),
        backend=backend,
        root=root,
        code_revision="a1b2c3d",
    )

    assert repeated == first
    assert len(backend.phase_calls) == phase_call_count
    assert len(backend.robustness_calls) == robustness_call_count


def test_resume_fails_closed_when_completed_stage_content_is_changed(tmp_path: Path) -> None:
    root = tmp_path / "lab"
    root.mkdir()
    backend = SyntheticAcceptedBackend()
    summary = run_research(
        proposal=FixtureProposalProvider(PROPOSAL).load(),
        dataset=_dataset(),
        backend=backend,
        root=root,
        code_revision="a1b2c3d",
    )
    variants_stage = summary.run_directory / "stages" / "02_VARIANTS_GENERATED.json"
    payload = json.loads(variants_stage.read_text(encoding="utf-8"))
    payload["payload"]["variants"][0]["content_sha256"] = "0" * 64
    variants_stage.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ResearchIntegrityError, match="STAGE_HASH_MISMATCH"):
        resume_research(
            experiment_id=summary.experiment_id,
            backend=backend,
            root=root,
            code_revision="a1b2c3d",
        )


def test_resume_starts_at_first_missing_stage_without_repeating_completed_work(
    tmp_path: Path,
) -> None:
    root = tmp_path / "lab"
    root.mkdir()
    backend = SyntheticAcceptedBackend()
    summary = run_research(
        proposal=FixtureProposalProvider(PROPOSAL).load(),
        dataset=_dataset(),
        backend=backend,
        root=root,
        code_revision="a1b2c3d",
    )
    stages = summary.run_directory / "stages"
    for path in sorted(stages.glob("*.json"), reverse=True):
        if path.name[:2] >= "05":
            path.unlink()
    completed_phase_calls = tuple(backend.phase_calls)
    completed_robustness_calls = tuple(backend.robustness_calls)

    with pytest.raises(ResearchIntegrityError, match="CODE_REVISION_MISMATCH"):
        resume_research(
            experiment_id=summary.experiment_id,
            backend=backend,
            root=root,
            code_revision="fffffff",
        )

    resumed = resume_research(
        experiment_id=summary.experiment_id,
        backend=backend,
        root=root,
        code_revision="a1b2c3d",
    )

    assert resumed == summary
    assert tuple(call for call in backend.phase_calls if call[0] != "final_test") == tuple(
        call for call in completed_phase_calls if call[0] != "final_test"
    )
    assert len(backend.robustness_calls) == 2 * len(completed_robustness_calls)


@pytest.mark.parametrize("command", ["run", "resume", "report"])
def test_research_cli_exposes_planned_commands(command: str) -> None:
    result = RUNNER.invoke(app, ["research", command, "--help"])

    assert result.exit_code == 0
    assert "--root" in result.stdout
    if command == "run":
        assert "--proposal" in result.stdout
        assert "--dataset-id" in result.stdout
    else:
        assert "--experiment-id" in result.stdout


def test_real_backend_converts_signal_and_trade_ledger_into_bounded_null_evidence() -> None:
    variant = generate_strategy_variants(FixtureProposalProvider(PROPOSAL).load())[0]
    session = date(2026, 7, 2)
    symbols = ("SPY", "QQQ", "IWM")
    events = tuple(
        BacktestEvent(
            sequence=index * 2 + slot,
            event_type="SIGNAL_ENTER_LONG",
            event_time=datetime(2026, 7, 2, 14, slot * 10, tzinfo=UTC),
            scenario="base",
            session=session,
            symbol=symbol,
            details=MappingProxyType({}),
        )
        for index, symbol in enumerate(symbols)
        for slot in range(2)
    )
    trades = tuple(
        TradeRecord(
            symbol=symbol,
            session=session,
            quantity=10,
            entry_time=datetime(2026, 7, 2, 14, 1, tzinfo=UTC),
            exit_time=datetime(2026, 7, 2, 14, 30, tzinfo=UTC),
            entry_price=100.0,
            exit_price=101.0,
            gross_pnl=10.0,
            net_pnl=9.0,
            cost_paid=1.0,
            forced=False,
        )
        for symbol in symbols
    )
    timestamps = pd.date_range("2026-07-02T14:00:00Z", periods=100, freq="min")
    minute_bars = pd.concat(
        [
            pd.DataFrame(
                {
                    "symbol": symbol,
                    "session_date": session,
                    "timestamp": timestamps,
                    "open": [100.0 + index * 0.01 for index in range(len(timestamps))],
                }
            )
            for symbol in symbols
        ],
        ignore_index=True,
    )
    run = SimpleNamespace(
        scenarios={
            "base": SimpleNamespace(
                events=events,
                trades=trades,
                metrics={"net_return": 0.01, "trade_count": 3.0},
            )
        }
    )

    evidence = orchestrator_module._null_evidence_from_run(
        variant=variant,
        run=run,
        minute_bars=minute_bars,
        initial_cash=100_000.0,
        result_sha256="e" * 64,
    )

    assert evidence.repetitions == 200
    assert len(evidence.evidence_opportunity_ids) == 6
    assert len(evidence.permutation_statistics) == 200
    assert len(evidence.timestamp_shift_statistics) == 200
    assert {
        key.rsplit(":", maxsplit=1)[-1] for key in evidence.trade_count_by_symbol_session
    } == set(symbols)
