import json
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Annotated, Never
from zoneinfo import ZoneInfo

import typer
from pydantic import ValidationError

from us_intraday_lab.backtest.clock import BacktestClock
from us_intraday_lab.backtest.costs import COST_SCENARIOS
from us_intraday_lab.backtest.engine import (
    ENGINE_ID,
    BacktestArtifactError,
    BacktestEngine,
    input_data_sha256,
    run_id_for_job,
    write_backtest_artifacts,
)
from us_intraday_lab.contracts.backtests import (
    BacktestFailureType,
    BacktestJob,
    CostModelIds,
    failed_backtest_result,
)
from us_intraday_lab.contracts.market import MarketBarClosed
from us_intraday_lab.contracts.paper import PaperSession
from us_intraday_lab.contracts.registry import RegistryState
from us_intraday_lab.contracts.strategies import StrategyDefinition
from us_intraday_lab.data.archive import (
    DEFAULT_ARCHIVE_READ_LIMITS,
    ArchiveReadLimits,
    inspect_archive,
)
from us_intraday_lab.data.catalog import (
    CatalogAcceptanceError,
    accept_dataset,
    build_catalog,
    connect_catalog,
)
from us_intraday_lab.data.snapshot import (
    ArchiveSourceDeclaration,
    import_snapshot,
    verify_snapshot,
)
from us_intraday_lab.factory.orchestrator import (
    BacktestResearchBackend,
    ResearchRunSummary,
    current_code_revision,
    load_accepted_research_dataset,
    load_research_inputs,
    resume_research,
    run_research,
)
from us_intraday_lab.factory.proposal import FixtureProposalProvider
from us_intraday_lab.long_horizon.catalog import (
    accept_five_minute_dataset,
    build_five_minute_catalog,
)
from us_intraday_lab.long_horizon.contracts import FiveMinuteSourceDeclaration
from us_intraday_lab.long_horizon.snapshot import (
    import_five_minute_snapshot,
    verify_five_minute_snapshot,
)
from us_intraday_lab.paper.alpaca_paper import AlpacaPaperBroker, PaperBoundaryError
from us_intraday_lab.paper.closeout import closeout_session
from us_intraday_lab.paper.market_data import (
    MARKET_SCHEMA_VERSION,
    AlpacaIexMinuteStream,
    MarketDataPipeline,
)
from us_intraday_lab.paper.reconciliation import run_startup_reconciliation
from us_intraday_lab.paper.session import CompiledSessionStrategy, PaperSessionService
from us_intraday_lab.paper.store import PaperStore
from us_intraday_lab.registry.store import RegistryStore
from us_intraday_lab.reporting.paper_daily import render_paper_daily_report
from us_intraday_lab.reporting.strategy_detail import render_strategy_detail_report
from us_intraday_lab.strategy.compiler import StrategyCompileError, compile_strategy
from us_intraday_lab.strategy.features import FEATURE_SET_VERSION
from us_intraday_lab.strategy.validator import scan_strategy_payload

app = typer.Typer(no_args_is_help=True)
data_app = typer.Typer(no_args_is_help=True)
long_horizon_data_app = typer.Typer(no_args_is_help=True)
backtest_app = typer.Typer(no_args_is_help=True)
research_app = typer.Typer(no_args_is_help=True)
paper_app = typer.Typer(no_args_is_help=True)
report_app = typer.Typer(no_args_is_help=True)
PAPER_SESSION_STATES: tuple[RegistryState, ...] = (
    "paper_shadow",
    "paper_observing",
    "paper_ranked",
    "leader",
)
app.add_typer(data_app, name="data")
app.add_typer(long_horizon_data_app, name="long-horizon-data")
app.add_typer(backtest_app, name="backtest")
app.add_typer(research_app, name="research")
app.add_typer(paper_app, name="paper")
app.add_typer(report_app, name="report")


def _paper_store(root: Path) -> PaperStore:
    return PaperStore(root / "state" / "paper" / "paper.sqlite3")


def _registry_store(root: Path) -> RegistryStore:
    path = root / "data" / "registry" / "strategy_registry.sqlite3"
    if not path.is_file():
        raise typer.BadParameter("strategy registry does not exist")
    return RegistryStore(path)


@report_app.command("paper-daily")
def report_paper_daily_command(
    session: Annotated[str, typer.Option("--session")],
    root: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)],
) -> None:
    """Render one evidence-only Chinese paper-session report."""

    try:
        session_date = date.fromisoformat(session)
        path = render_paper_daily_report(
            root=root,
            paper_store=_paper_store(root),
            registry_store=_registry_store(root),
            session_date=session_date,
        )
    except ValueError as error:
        raise typer.BadParameter(f"paper daily report failed: {error}") from error
    typer.echo(path)


@report_app.command("strategy")
def report_strategy_command(
    strategy_id: Annotated[str, typer.Option("--strategy-id")],
    root: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)],
) -> None:
    """Render one evidence-only Chinese paper-strategy dossier."""

    try:
        path = render_strategy_detail_report(
            root=root,
            paper_store=_paper_store(root),
            registry_store=_registry_store(root),
            strategy_id=strategy_id,
        )
    except ValueError as error:
        raise typer.BadParameter(f"strategy report failed: {error}") from error
    typer.echo(path)


def _latest_paper_session(store: PaperStore) -> PaperSession:
    sessions = store.list_sessions()
    if not sessions:
        raise typer.BadParameter("no paper session exists; run paper run first")
    return sessions[-1]


@paper_app.command("preflight")
def paper_preflight_command(
    root: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)],
) -> None:
    """Prove paper-only broker, schema, session, and writable ignored state."""

    try:
        broker = AlpacaPaperBroker.from_environment()
    except PaperBoundaryError as error:
        raise typer.BadParameter(str(error)) from error
    account = broker.account()
    clock = broker.clock()
    store = _paper_store(root)
    required_tables = {
        "paper_sessions",
        "market_events",
        "order_intents",
        "order_events",
        "position_snapshots",
        "reconciliation_runs",
        "incident_events",
    }
    missing = sorted(required_tables.difference(store.table_names()))
    sessions = store.list_sessions()
    registry_path = root / "data" / "registry" / "strategy_registry.sqlite3"
    enabled_strategy_count = 0
    if registry_path.exists():
        enabled_strategy_count = len(
            RegistryStore(registry_path).list_strategy_definitions_in_states(PAPER_SESSION_STATES)
        )
    session = None if not sessions else sessions[-1]
    reconciliation_status = "missing_session"
    if session is not None:
        reconciliation_status = run_startup_reconciliation(
            store=store,
            broker=broker,
            paper_session_id=session.paper_session_id,
            completed_at=datetime.now(UTC),
        ).status
    state_ignored = (
        subprocess.run(
            ["git", "check-ignore", "-q", str(store.path)],
            cwd=root,
            check=False,
        ).returncode
        == 0
    )
    readiness_blockers: list[str] = []
    if not registry_path.exists():
        readiness_blockers.append("STRATEGY_REGISTRY_MISSING")
    if enabled_strategy_count == 0:
        readiness_blockers.append("NO_ENABLED_PAPER_STRATEGY")
    if session is None:
        readiness_blockers.append("PAPER_SESSION_NOT_STARTED")
    elif reconciliation_status != "clean":
        readiness_blockers.append("RECONCILIATION_NOT_CLEAN")
    preflight_passed = (
        not missing
        and enabled_strategy_count <= 20
        and state_ignored
        and reconciliation_status in {"missing_session", "clean"}
    )
    ready_for_paper_run = preflight_passed and not readiness_blockers
    result = {
        "environment": "paper",
        "broker_endpoint": broker.endpoint,
        "broker_account_id": account.account_id,
        "broker_clock_open": clock.is_open,
        "production_symbols": ["SPY", "QQQ", "IWM"],
        "paper_session_id": None if session is None else session.paper_session_id,
        "paper_session_status": None if session is None else session.status,
        "schema_complete": not missing,
        "market_schema_version": MARKET_SCHEMA_VERSION,
        "feature_set_version": FEATURE_SET_VERSION,
        "missing_tables": missing,
        "state_path": str(store.path),
        "state_path_writable": True,
        "state_path_git_ignored": state_ignored,
        "preflight_submitted_orders": 0,
        "enabled_strategy_count": enabled_strategy_count,
        "strategy_capacity_ok": enabled_strategy_count <= 20,
        "reconciliation_status": reconciliation_status,
        "preflight_passed": preflight_passed,
        "ready_for_paper_run": ready_for_paper_run,
        "readiness_blockers": readiness_blockers,
    }
    typer.echo(json.dumps(result, sort_keys=True))
    if not preflight_passed:
        raise typer.Exit(code=1)


@paper_app.command("reconcile")
def paper_reconcile_command(
    root: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)],
) -> None:
    """Compare durable local paper evidence with current Alpaca paper truth."""

    store = _paper_store(root)
    session = _latest_paper_session(store)
    result = run_startup_reconciliation(
        store=store,
        broker=AlpacaPaperBroker.from_environment(),
        paper_session_id=session.paper_session_id,
        completed_at=datetime.now(UTC),
    )
    typer.echo(result.model_dump_json())


@paper_app.command("closeout")
def paper_closeout_command(
    root: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)],
) -> None:
    """Cancel opening orders and flatten every Alpaca paper long position."""

    store = _paper_store(root)
    session = _latest_paper_session(store)
    result = closeout_session(
        broker=AlpacaPaperBroker.from_environment(),
        store=store,
        paper_session_id=session.paper_session_id,
        strategy_ids_by_symbol={},
        closeout_at=datetime.now(UTC),
        max_cancel_polls=3,
        max_exit_attempts=3,
        max_flat_polls=3,
    )
    typer.echo(json.dumps({"clean": result.clean, "status": result.status}, sort_keys=True))


@paper_app.command("run")
def paper_run_command(
    root: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)],
) -> None:
    """Start or resume the automated Alpaca IEX paper session."""

    broker = AlpacaPaperBroker.from_environment()
    now = datetime.now(UTC)
    session_date = now.astimezone(ZoneInfo("America/New_York")).date()
    clock = BacktestClock(session_date=session_date, closeout_buffer_minutes=5)
    account = broker.account()
    store = _paper_store(root)
    session_id = f"paper-{session_date.isoformat()}"
    session = store.get_session(session_id)
    if session is None:
        session = store.create_session(
            PaperSession(
                paper_session_id=session_id,
                session_date=session_date,
                broker_account_id=account.account_id,
                broker_sdk_version=account.broker_sdk_version,
                status="running",
                created_at=now,
            )
        )
    registry_path = root / "data" / "registry" / "strategy_registry.sqlite3"
    if not registry_path.exists():
        raise typer.BadParameter("strategy registry does not exist")
    enabled = RegistryStore(registry_path).list_strategy_definitions_in_states(PAPER_SESSION_STATES)
    if not enabled:
        raise typer.BadParameter("no enabled paper lifecycle strategy exists")
    if len(enabled) > 20:
        raise typer.BadParameter("paper observing capacity exceeds 20 strategies")
    history = tuple(
        event for event in store.list_market_events(session_id) if event.timeframe == "15min"
    )
    strategies = tuple(
        CompiledSessionStrategy(
            compiled=compile_strategy(definition),
            symbol=symbol,
            lifecycle_state=state,
            history=history,
        )
        for definition, state in enabled
        for symbol in definition.symbols
    )
    pipeline = MarketDataPipeline(
        store=store,
        paper_session_id=session_id,
        session_date=session_date,
        reorder_window=timedelta(minutes=2),
        stale_after=timedelta(minutes=2),
        expected_market_schema_version="1.0.0",
        expected_feature_set_version=FEATURE_SET_VERSION,
    )
    service = PaperSessionService(
        store=store,
        broker=broker,
        market_data=pipeline,
        strategies=strategies,
        session_date=session_date,
        closeout_buffer_minutes=5,
    )
    result = service.start(completed_at=now)
    if result.status != "clean":
        typer.echo(result.model_dump_json(), err=True)
        raise typer.Exit(code=1)
    typer.echo(
        json.dumps(
            {
                "paper_session_id": session.paper_session_id,
                "status": "running",
                "market_provider": "alpaca",
                "market_feed": "iex",
            },
            sort_keys=True,
        )
    )
    closed = False

    def on_bar(bar: object) -> None:
        nonlocal closed
        if not isinstance(bar, MarketBarClosed):
            raise TypeError("paper market stream emitted an invalid bar")
        observed_at = datetime.now(UTC)
        session_result = service.process_bars((bar,), observed_at=observed_at)
        if session_result.reason_codes:
            typer.echo(
                json.dumps(
                    {
                        "entries_enabled": session_result.entries_enabled,
                        "reason_codes": session_result.reason_codes,
                    },
                    sort_keys=True,
                ),
                err=True,
            )
        if not closed and observed_at >= clock.closeout_time:
            closed = True
            closeout = service.closeout(closeout_at=observed_at)
            typer.echo(
                json.dumps(
                    {"closeout_clean": closeout.clean, "status": closeout.status},
                    sort_keys=True,
                )
            )

    AlpacaIexMinuteStream.from_environment().run(on_bar)


@data_app.command("diagnose-sip-difference")
def diagnose_sip_difference_command(
    session: Annotated[str, typer.Option()],
    root: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)],
) -> None:
    """Diagnostic-only SIP comparison; never writes production paper bars."""

    typer.echo(
        json.dumps(
            {
                "mode": "diagnostic-only",
                "session": session,
                "root": str(root.resolve()),
                "production_feed_unchanged": "alpaca/iex",
            },
            sort_keys=True,
        )
    )


def _archive_limits(
    *,
    max_approved_members: int,
    max_selected_uncompressed_bytes: int,
    max_imported_rows: int,
    parquet_spool_memory_bytes: int,
) -> ArchiveReadLimits:
    return ArchiveReadLimits(
        max_approved_members=max_approved_members,
        max_selected_uncompressed_bytes=max_selected_uncompressed_bytes,
        max_imported_rows=max_imported_rows,
        parquet_spool_memory_bytes=parquet_spool_memory_bytes,
    )


def _robustness_group(value: str) -> tuple[str, date]:
    try:
        symbol, session_date = value.rsplit(":", maxsplit=1)
        return symbol, date.fromisoformat(session_date)
    except ValueError as error:
        raise typer.BadParameter("expected robustness groups must use SYMBOL:YYYY-MM-DD") from error


@data_app.command("inspect-archive")
def inspect_archive_command(
    archive: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
    max_approved_members: Annotated[
        int, typer.Option()
    ] = DEFAULT_ARCHIVE_READ_LIMITS.max_approved_members,
    max_selected_uncompressed_bytes: Annotated[
        int, typer.Option()
    ] = DEFAULT_ARCHIVE_READ_LIMITS.max_selected_uncompressed_bytes,
    max_imported_rows: Annotated[
        int, typer.Option()
    ] = DEFAULT_ARCHIVE_READ_LIMITS.max_imported_rows,
    parquet_spool_memory_bytes: Annotated[
        int, typer.Option()
    ] = DEFAULT_ARCHIVE_READ_LIMITS.parquet_spool_memory_bytes,
) -> None:
    inspection = inspect_archive(
        archive,
        limits=_archive_limits(
            max_approved_members=max_approved_members,
            max_selected_uncompressed_bytes=max_selected_uncompressed_bytes,
            max_imported_rows=max_imported_rows,
            parquet_spool_memory_bytes=parquet_spool_memory_bytes,
        ),
    )
    typer.echo(f"archive: {inspection.archive}")
    typer.echo(f"source_sha256: {inspection.source_sha256}")
    for member in inspection.members:
        typer.echo(f"member: {member.name}")
        typer.echo(f"  size_bytes: {member.size}")
        typer.echo(f"  sha256: {member.sha256}")
        typer.echo(f"  row_estimate: {member.row_estimate}")
        typer.echo(f"  columns: {','.join(member.columns)}")
        typer.echo(f"  min_timestamp: {member.min_timestamp}")
        typer.echo(f"  max_timestamp: {member.max_timestamp}")
        typer.echo(f"  symbol_count: {len(member.symbols)}")
    typer.echo(f"row_estimate: {inspection.row_estimate}")
    typer.echo(f"min_timestamp: {inspection.min_timestamp}")
    typer.echo(f"max_timestamp: {inspection.max_timestamp}")
    typer.echo(f"symbol_count: {len(inspection.symbols)}")
    typer.echo(f"symbols: {','.join(inspection.symbols)}")


@data_app.command("import-archive")
def import_archive_command(
    archive: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
    root: Annotated[Path, typer.Option(file_okay=False)],
    provider: Annotated[str, typer.Option()],
    feed: Annotated[str, typer.Option()],
    bar_size: Annotated[str, typer.Option()],
    member: Annotated[list[str], typer.Option("--member")],
    production_symbol: Annotated[list[str], typer.Option("--production-symbol")],
    expected_start_date: Annotated[str, typer.Option()],
    expected_end_date: Annotated[str, typer.Option()],
    ingested_at: Annotated[str, typer.Option()],
    expected_robustness_group: Annotated[
        list[str] | None, typer.Option("--expected-robustness-group")
    ] = None,
    max_approved_members: Annotated[
        int, typer.Option()
    ] = DEFAULT_ARCHIVE_READ_LIMITS.max_approved_members,
    max_selected_uncompressed_bytes: Annotated[
        int, typer.Option()
    ] = DEFAULT_ARCHIVE_READ_LIMITS.max_selected_uncompressed_bytes,
    max_imported_rows: Annotated[
        int, typer.Option()
    ] = DEFAULT_ARCHIVE_READ_LIMITS.max_imported_rows,
    parquet_spool_memory_bytes: Annotated[
        int, typer.Option()
    ] = DEFAULT_ARCHIVE_READ_LIMITS.parquet_spool_memory_bytes,
) -> None:
    source = ArchiveSourceDeclaration(
        provider=provider,
        feed=feed,
        bar_size=bar_size,
        member_names=tuple(member),
        production_symbols=tuple(production_symbol),
        expected_start_date=date.fromisoformat(expected_start_date),
        expected_end_date=date.fromisoformat(expected_end_date),
        ingested_at=datetime.fromisoformat(ingested_at),
        expected_robustness_groups=tuple(
            _robustness_group(value) for value in (expected_robustness_group or [])
        ),
    )
    manifest, _ = import_snapshot(
        archive,
        root=root,
        source=source,
        limits=_archive_limits(
            max_approved_members=max_approved_members,
            max_selected_uncompressed_bytes=max_selected_uncompressed_bytes,
            max_imported_rows=max_imported_rows,
            parquet_spool_memory_bytes=parquet_spool_memory_bytes,
        ),
    )
    typer.echo(manifest.dataset_id)


@data_app.command("verify-snapshot")
def verify_snapshot_command(
    dataset_id: Annotated[str, typer.Option()],
    root: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)],
) -> None:
    manifest = verify_snapshot(dataset_id, root=root)
    typer.echo(manifest.dataset_id)


@data_app.command("build-catalog")
def build_catalog_command(
    dataset_id: Annotated[str, typer.Option()],
    root: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)],
) -> None:
    typer.echo(build_catalog(dataset_id, root=root))


@data_app.command("accept")
def accept_dataset_command(
    dataset_id: Annotated[str, typer.Option()],
    root: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)],
) -> None:
    summary = accept_dataset(dataset_id, root=root)
    typer.echo(f"dataset_id: {summary.dataset_id}")
    typer.echo(f"quality_passed: {str(summary.quality_passed).lower()}")
    typer.echo(f"production_symbols: {','.join(summary.production_symbols)}")
    typer.echo(f"bars_1m: {summary.bar_counts['1min']}")
    typer.echo(f"bars_5m: {summary.bar_counts['5min']}")
    typer.echo(f"bars_15m: {summary.bar_counts['15min']}")


@long_horizon_data_app.command("import")
def import_long_horizon_data_command(
    archive: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
    root: Annotated[Path, typer.Option(file_okay=False)],
    member_sha256: Annotated[str, typer.Option()] = (
        "2aa6d1483d4aed73edad83c255f837ca95004cb9230108966ae825074289e669"
    ),
    expected_start_date: Annotated[str, typer.Option()] = "2025-01-02",
    expected_end_date: Annotated[str, typer.Option()] = "2026-07-02",
    ingested_at: Annotated[str, typer.Option()] = "2026-08-08T00:00:00+00:00",
    code_revision: Annotated[str | None, typer.Option()] = None,
) -> None:
    """Import the closed AAPL/QQQ legacy five-minute source."""

    declaration = FiveMinuteSourceDeclaration(
        provider="tiingo",
        feed="iex",
        bar_size="5min",
        member_name="price_intraday_vol_5min.csv",
        member_sha256=member_sha256,
        symbols=("AAPL", "QQQ"),
        source_timezone="America/New_York",
        expected_start_date=date.fromisoformat(expected_start_date),
        expected_end_date=date.fromisoformat(expected_end_date),
        ingested_at=datetime.fromisoformat(ingested_at),
    )
    manifest = import_five_minute_snapshot(
        archive,
        declaration,
        root=root,
        code_revision=code_revision or current_code_revision(root),
    )
    typer.echo(manifest.dataset_id)


@long_horizon_data_app.command("verify")
def verify_long_horizon_data_command(
    dataset_id: Annotated[str, typer.Option()],
    root: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)],
) -> None:
    manifest = verify_five_minute_snapshot(dataset_id, root=root)
    typer.echo(manifest.dataset_id)


@long_horizon_data_app.command("build-catalog")
def build_long_horizon_catalog_command(
    dataset_id: Annotated[str, typer.Option()],
    root: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)],
) -> None:
    typer.echo(build_five_minute_catalog(dataset_id, root=root))


@long_horizon_data_app.command("accept")
def accept_long_horizon_data_command(
    dataset_id: Annotated[str, typer.Option()],
    root: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)],
) -> None:
    summary = accept_five_minute_dataset(dataset_id, root=root)
    typer.echo(
        json.dumps(
            {
                "accepted_sessions": summary.accepted_sessions,
                "dataset_id": summary.dataset_id,
                "missing_expected_bars": summary.missing_expected_bars,
                "row_count": summary.row_count,
                "symbols": list(summary.symbols),
            },
            sort_keys=True,
        )
    )


def _load_strategy(path: Path) -> StrategyDefinition:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise typer.BadParameter(f"strategy JSON could not be read: {error}") from error
    safety = scan_strategy_payload(payload)
    if not safety.passed:
        reasons = ",".join(f"{issue.code}:{issue.path}" for issue in safety.issues)
        raise typer.BadParameter(f"strategy failed static safety validation: {reasons}")
    try:
        return StrategyDefinition.model_validate(payload)
    except ValidationError as error:
        raise typer.BadParameter(f"strategy contract validation failed: {error}") from error


def _exit_with_backtest_failure(
    *,
    failure_type: BacktestFailureType,
    error: object,
    dataset_id: str,
    strategy_path: Path,
    job: BacktestJob | None = None,
) -> Never:
    result = failed_backtest_result(
        failure_type=failure_type,
        message=str(error).strip() or type(error).__name__,
        job_id=job.job_id if job is not None else None,
        run_id=run_id_for_job(job) if job is not None else None,
        context={
            "dataset_id": dataset_id,
            "strategy_path": strategy_path.as_posix(),
        },
    )
    typer.echo(result.model_dump_json(), err=True)
    raise typer.Exit(code=1)


@backtest_app.command("run")
def run_backtest_command(
    strategy: Annotated[
        Path,
        typer.Option(),
    ],
    dataset_id: Annotated[str, typer.Option()],
    initial_cash: Annotated[float, typer.Option()],
    root: Annotated[
        Path,
        typer.Option(),
    ],
    closeout_buffer_minutes: Annotated[int, typer.Option()] = 5,
) -> None:
    """Run all v1 cost scenarios against one accepted immutable dataset."""
    job: BacktestJob | None = None
    try:
        accept_dataset(dataset_id, root=root)
        manifest = verify_snapshot(dataset_id, root=root)
    except (CatalogAcceptanceError, OSError, ValueError) as error:
        _exit_with_backtest_failure(
            failure_type="dataset_validation",
            error=error,
            dataset_id=dataset_id,
            strategy_path=strategy,
        )
    try:
        definition = _load_strategy(strategy)
        compiled = compile_strategy(definition)
    except (
        StrategyCompileError,
        ValidationError,
        ValueError,
        OSError,
        typer.BadParameter,
    ) as error:
        _exit_with_backtest_failure(
            failure_type="strategy_validation",
            error=error,
            dataset_id=dataset_id,
            strategy_path=strategy,
        )
    try:
        with connect_catalog(root=root) as connection:
            minute_bars = connection.execute(
                """
                SELECT *
                FROM bars_1m
                ORDER BY session_date, timestamp, symbol
                """
            ).df()
            signal_bars = connection.execute(
                """
                SELECT *
                FROM bars_15m
                ORDER BY session_date, available_at, symbol
                """
            ).df()
    except Exception as error:  # noqa: BLE001 - catalog boundary returns typed failure
        _exit_with_backtest_failure(
            failure_type="dataset_validation",
            error=error,
            dataset_id=dataset_id,
            strategy_path=strategy,
        )
    try:
        job = BacktestJob.create(
            schema_version="1.0.0",
            strategy_id=compiled.definition_fingerprint,
            dataset_id=manifest.dataset_id,
            engine_id=ENGINE_ID,
            calendar_id=f"{manifest.calendar_name}@{manifest.calendar_version}",
            input_data_sha256=input_data_sha256(minute_bars, signal_bars),
            initial_cash=initial_cash,
            closeout_buffer_minutes=closeout_buffer_minutes,
            cost_model_ids=CostModelIds(
                optimistic=COST_SCENARIOS["optimistic"].model_id,
                base=COST_SCENARIOS["base"].model_id,
                stress=COST_SCENARIOS["stress"].model_id,
            ),
        )
    except (ValidationError, ValueError, TypeError) as error:
        _exit_with_backtest_failure(
            failure_type="execution",
            error=error,
            dataset_id=dataset_id,
            strategy_path=strategy,
        )

    try:
        run = BacktestEngine(job=job, strategy=compiled).run(
            minute_bars=minute_bars,
            signal_bars=signal_bars,
        )
    except Exception as error:  # noqa: BLE001 - CLI boundary must return a typed failure
        _exit_with_backtest_failure(
            failure_type="execution",
            error=error,
            dataset_id=dataset_id,
            strategy_path=strategy,
            job=job,
        )
    try:
        result_path = write_backtest_artifacts(run, root=root)
    except BacktestArtifactError as error:
        typer.echo(error.result.model_dump_json(), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(result_path)


@research_app.command("run")
def run_research_command(
    proposal: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
    dataset_id: Annotated[str, typer.Option()],
    root: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)],
) -> None:
    """Run or idempotently resume one immutable proposal/dataset experiment."""

    try:
        hypothesis = FixtureProposalProvider(proposal).load()
        dataset = load_accepted_research_dataset(root=root, dataset_id=dataset_id)
        summary = run_research(
            proposal=hypothesis,
            dataset=dataset,
            backend=BacktestResearchBackend(root=root, dataset=dataset),
            root=root,
            code_revision=current_code_revision(root),
        )
    except Exception as error:
        raise typer.BadParameter(f"research run failed: {error}") from error
    typer.echo(f"experiment_id: {summary.experiment_id}")
    typer.echo(f"report: {summary.report_path}")


def _resume_from_id(*, experiment_id: str, root: Path) -> ResearchRunSummary:
    _proposal, dataset, _manifest = load_research_inputs(
        experiment_id=experiment_id,
        root=root,
    )
    return resume_research(
        experiment_id=experiment_id,
        backend=BacktestResearchBackend(root=root, dataset=dataset),
        root=root,
        code_revision=current_code_revision(root),
    )


@research_app.command("resume")
def resume_research_command(
    experiment_id: Annotated[str, typer.Option()],
    root: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)],
) -> None:
    """Verify completed stages and continue from the first missing stage."""

    try:
        summary = _resume_from_id(experiment_id=experiment_id, root=root)
    except Exception as error:
        raise typer.BadParameter(f"research resume failed: {error}") from error
    typer.echo(f"experiment_id: {summary.experiment_id}")
    typer.echo(f"report: {summary.report_path}")


@research_app.command("report")
def report_research_command(
    experiment_id: Annotated[str, typer.Option()],
    root: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)],
) -> None:
    """Verify stored evidence and print the evidence-only Chinese report path."""

    try:
        summary = _resume_from_id(experiment_id=experiment_id, root=root)
    except Exception as error:
        raise typer.BadParameter(f"research report failed: {error}") from error
    typer.echo(summary.report_path)


if __name__ == "__main__":
    app()
