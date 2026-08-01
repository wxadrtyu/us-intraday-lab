import os
import subprocess
from datetime import UTC, date, datetime
from math import sqrt
from pathlib import Path
from types import MappingProxyType

import pytest

import us_intraday_lab.backtest.engine as engine_module
from us_intraday_lab.backtest.costs import COST_SCENARIOS
from us_intraday_lab.backtest.engine import (
    BacktestArtifactError,
    BacktestEvent,
    EngineRun,
    ScenarioRun,
    run_id_for_job,
    write_backtest_artifacts,
)
from us_intraday_lab.backtest.metrics import (
    EquityPoint,
    TradeRecord,
    compute_metrics,
)
from us_intraday_lab.contracts.backtests import BacktestJob, CostModelIds


def _time(day: int, hour: int, minute: int) -> datetime:
    return datetime(2026, 7, day, hour, minute, tzinfo=UTC)


def test_metrics_use_net_trade_pnl_and_session_close_returns() -> None:
    trades = (
        TradeRecord(
            symbol="SPY",
            session=date(2026, 7, 2),
            quantity=10,
            entry_time=_time(2, 14, 0),
            exit_time=_time(2, 15, 0),
            entry_price=100.0,
            exit_price=102.0,
            gross_pnl=22.0,
            net_pnl=20.0,
            cost_paid=2.0,
            forced=False,
        ),
        TradeRecord(
            symbol="QQQ",
            session=date(2026, 7, 6),
            quantity=5,
            entry_time=_time(6, 14, 0),
            exit_time=_time(6, 15, 0),
            entry_price=200.0,
            exit_price=198.0,
            gross_pnl=-9.0,
            net_pnl=-10.0,
            cost_paid=1.0,
            forced=True,
        ),
    )
    equity = (
        EquityPoint(_time(2, 14, 0), date(2026, 7, 2), 1_000.0, 500.0),
        EquityPoint(_time(2, 20, 0), date(2026, 7, 2), 1_020.0, 0.0),
        EquityPoint(_time(6, 14, 0), date(2026, 7, 6), 1_020.0, 510.0),
        EquityPoint(_time(6, 20, 0), date(2026, 7, 6), 1_010.0, 0.0),
    )

    metrics = compute_metrics(trades, equity, initial_cash=1_000.0)

    session_returns = (0.02, 1_010.0 / 1_020.0 - 1.0)
    mean_return = sum(session_returns) / 2
    sample_variance = sum((value - mean_return) ** 2 for value in session_returns)
    sample_std = sqrt(sample_variance)
    assert metrics["net_return"] == pytest.approx(0.01)
    assert metrics["annualized_volatility"] == pytest.approx(sample_std * sqrt(252.0))
    assert metrics["sharpe"] == pytest.approx(mean_return / sample_std * sqrt(252.0))
    assert metrics["max_drawdown"] == pytest.approx(1.0 - 1_010.0 / 1_020.0)
    assert metrics["profit_factor"] == pytest.approx(2.0)
    assert metrics["win_rate"] == pytest.approx(0.5)
    assert metrics["expectancy"] == pytest.approx(5.0)
    assert metrics["trade_count"] == 2.0
    assert metrics["exposure"] == pytest.approx(0.25)
    assert metrics["turnover"] == pytest.approx(4.01)
    assert metrics["cost_paid"] == pytest.approx(3.0)
    assert metrics["pnl_by_symbol:SPY"] == pytest.approx(20.0)
    assert metrics["pnl_by_symbol:QQQ"] == pytest.approx(-10.0)
    assert metrics["pnl_by_session:2026-07-02"] == pytest.approx(20.0)
    assert metrics["pnl_by_session:2026-07-06"] == pytest.approx(-10.0)


def test_metrics_are_finite_and_descriptive_when_no_trade_statistics_exist() -> None:
    metrics = compute_metrics(
        (),
        (
            EquityPoint(
                _time(2, 20, 0),
                date(2026, 7, 2),
                25_000.0,
                0.0,
            ),
        ),
        initial_cash=25_000.0,
    )

    assert metrics == {
        "annualized_volatility": 0.0,
        "cost_paid": 0.0,
        "expectancy": 0.0,
        "exposure": 0.0,
        "max_drawdown": 0.0,
        "net_return": 0.0,
        "profit_factor": 0.0,
        "sharpe": 0.0,
        "trade_count": 0.0,
        "turnover": 0.0,
        "win_rate": 0.0,
    }


def test_metrics_reject_nonpositive_initial_cash() -> None:
    with pytest.raises(ValueError, match="initial_cash"):
        compute_metrics((), (), initial_cash=0.0)


def _empty_run() -> EngineRun:
    job = BacktestJob.create(
        schema_version="1.0.0",
        strategy_id="strategy@sha256:" + "a" * 64,
        dataset_id="accepted-dataset",
        engine_id="event-engine-1.0.0",
        calendar_id="XNYS@4.11",
        initial_cash=25_000.0,
        closeout_buffer_minutes=5,
        cost_model_ids=CostModelIds(
            optimistic=COST_SCENARIOS["optimistic"].model_id,
            base=COST_SCENARIOS["base"].model_id,
            stress=COST_SCENARIOS["stress"].model_id,
        ),
    )
    run_id = run_id_for_job(job)
    scenarios = {}
    for scenario in ("optimistic", "base", "stress"):
        scenarios[scenario] = ScenarioRun(
            cost_scenario=scenario,
            events=(
                BacktestEvent(
                    sequence=1,
                    event_type="SESSION_FINALIZED",
                    event_time=_time(2, 20, 0),
                    scenario=scenario,
                    session=date(2026, 7, 2),
                    symbol=None,
                    details=MappingProxyType(
                        {
                            "cash": 25_000.0,
                            "equity": 25_000.0,
                            "order_count": 0,
                            "position_count": 0,
                        }
                    ),
                ),
            ),
            intents=(),
            trades=(),
            equity_curve=(
                EquityPoint(
                    _time(2, 20, 0),
                    date(2026, 7, 2),
                    25_000.0,
                    0.0,
                ),
            ),
            initial_cash=25_000.0,
            final_cash=25_000.0,
            final_positions=(),
        )
    run = EngineRun(
        job=job,
        run_id=run_id,
        scenarios=MappingProxyType(scenarios),
    )
    return run


def test_artifact_writer_publishes_only_after_complete_sibling_is_written(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _empty_run()
    final = tmp_path / "artifacts" / "backtests" / run.run_id
    original_rename = Path.rename
    observed = False

    def assert_complete_before_publish(source: Path, target: Path) -> Path:
        nonlocal observed
        if target == final:
            observed = True
            assert source.parent == final.parent
            assert not final.exists()
            assert {path.name for path in source.iterdir()} == {
                "events.jsonl",
                "job.json",
                "result.json",
                "trades.jsonl",
            }
        return original_rename(source, target)

    monkeypatch.setattr(Path, "rename", assert_complete_before_publish)

    result_path = write_backtest_artifacts(run, root=tmp_path)

    assert observed
    assert result_path == final / "result.json"


def test_artifact_writer_persists_events_and_trades_before_metrics(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _empty_run()
    original_compute = engine_module.compute_metrics
    observed_calls = 0

    def assert_inputs_are_already_persisted(*args: object, **kwargs: object) -> dict[str, float]:
        nonlocal observed_calls
        observed_calls += 1
        temporary = next((tmp_path / "artifacts" / "backtests").glob(f".{run.run_id}-*"))
        assert (temporary / "events.jsonl").is_file()
        assert (temporary / "trades.jsonl").is_file()
        return original_compute(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(engine_module, "compute_metrics", assert_inputs_are_already_persisted)

    write_backtest_artifacts(run, root=tmp_path)

    assert observed_calls == 3


def test_artifact_writer_cleans_temporary_directory_and_returns_typed_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _empty_run()
    original_write_text = Path.write_text

    def fail_on_job(path: Path, data: str, *args: object, **kwargs: object) -> int:
        if path.name == "job.json":
            raise OSError("simulated disk failure")
        return original_write_text(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_on_job)

    with pytest.raises(BacktestArtifactError) as exc_info:
        write_backtest_artifacts(run, root=tmp_path)

    parent = tmp_path / "artifacts" / "backtests"
    assert exc_info.value.failure.failure_type == "artifact_write"
    assert not (parent / run.run_id).exists()
    assert not list(parent.glob(f".{run.run_id}-*"))


def test_artifact_writer_is_idempotent_only_for_identical_complete_content(
    tmp_path: Path,
) -> None:
    run = _empty_run()
    first = write_backtest_artifacts(run, root=tmp_path)

    assert write_backtest_artifacts(run, root=tmp_path) == first
    (first.parent / "job.json").write_text("{}\n", encoding="utf-8")

    with pytest.raises(BacktestArtifactError, match="different content") as exc_info:
        write_backtest_artifacts(run, root=tmp_path)

    assert exc_info.value.failure.failure_type == "artifact_write"
    assert (first.parent / "job.json").read_text(encoding="utf-8") == "{}\n"


def test_artifact_writer_rejects_symlink_escape_from_artifact_tree(tmp_path: Path) -> None:
    run = _empty_run()
    outside = tmp_path / "outside"
    outside.mkdir()
    artifacts = tmp_path / "artifacts"
    try:
        artifacts.symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks unavailable: {error}")

    with pytest.raises(BacktestArtifactError, match="reparse|symlink|escape"):
        write_backtest_artifacts(run, root=tmp_path)

    assert not (outside / "backtests" / run.run_id).exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows junction security case")
def test_artifact_writer_rejects_junction_escape_from_artifact_tree(tmp_path: Path) -> None:
    run = _empty_run()
    outside = tmp_path / "junction-outside"
    outside.mkdir()
    artifacts = tmp_path / "artifacts"
    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(artifacts), str(outside)],
        check=False,
        capture_output=True,
        text=True,
    )
    if created.returncode != 0:
        pytest.skip(f"junction creation unavailable: {created.stderr}")
    try:
        with pytest.raises(BacktestArtifactError, match="reparse"):
            write_backtest_artifacts(run, root=tmp_path)
        assert not (outside / "backtests" / run.run_id).exists()
    finally:
        artifacts.rmdir()


def test_artifact_writer_rejects_forged_run_id_before_path_construction(
    tmp_path: Path,
) -> None:
    run = _empty_run()
    forged = EngineRun(
        job=run.job,
        run_id="../escape",
        scenarios=run.scenarios,
    )

    with pytest.raises(BacktestArtifactError, match="canonical BacktestJob") as exc_info:
        write_backtest_artifacts(forged, root=tmp_path)

    assert exc_info.value.result.run_id == run.run_id
    assert exc_info.value.result.events_uri is None
    assert exc_info.value.result.trades_uri is None
    assert not (tmp_path / "artifacts").exists()


def test_cleanup_failure_preserves_primary_error_and_canonical_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _empty_run()
    original_write_text = Path.write_text
    original_rmtree = engine_module.shutil.rmtree

    def fail_on_job(path: Path, data: str, *args: object, **kwargs: object) -> int:
        if path.name == "job.json":
            raise OSError("primary write failure")
        return original_write_text(path, data, *args, **kwargs)

    def fail_cleanup(path: Path, *args: object, **kwargs: object) -> None:
        raise OSError("cleanup failure")

    monkeypatch.setattr(Path, "write_text", fail_on_job)
    monkeypatch.setattr(engine_module.shutil, "rmtree", fail_cleanup)

    with pytest.raises(BacktestArtifactError, match="primary write failure") as exc_info:
        write_backtest_artifacts(run, root=tmp_path)

    assert exc_info.value.result.job_id == run.job.job_id
    assert exc_info.value.result.run_id == run.run_id
    assert any("cleanup failure" in note for note in exc_info.value.__notes__)

    monkeypatch.setattr(engine_module.shutil, "rmtree", original_rmtree)
    for temporary in (tmp_path / "artifacts" / "backtests").glob(f".{run.run_id}-*"):
        original_rmtree(temporary)
