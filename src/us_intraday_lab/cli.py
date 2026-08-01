import json
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Never

import typer
from pydantic import ValidationError

from us_intraday_lab.backtest.costs import COST_SCENARIOS
from us_intraday_lab.backtest.engine import (
    ENGINE_ID,
    BacktestArtifactError,
    BacktestEngine,
    run_id_for_job,
    write_backtest_artifacts,
)
from us_intraday_lab.contracts.backtests import (
    BacktestFailureType,
    BacktestJob,
    CostModelIds,
    failed_backtest_result,
)
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
from us_intraday_lab.strategy.compiler import StrategyCompileError, compile_strategy
from us_intraday_lab.strategy.validator import scan_strategy_payload

app = typer.Typer(no_args_is_help=True)
data_app = typer.Typer(no_args_is_help=True)
backtest_app = typer.Typer(no_args_is_help=True)
app.add_typer(data_app, name="data")
app.add_typer(backtest_app, name="backtest")


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
        job = BacktestJob.create(
            schema_version="1.0.0",
            strategy_id=compiled.definition_fingerprint,
            dataset_id=manifest.dataset_id,
            engine_id=ENGINE_ID,
            calendar_id=f"{manifest.calendar_name}@{manifest.calendar_version}",
            initial_cash=initial_cash,
            closeout_buffer_minutes=closeout_buffer_minutes,
            cost_model_ids=CostModelIds(
                optimistic=COST_SCENARIOS["optimistic"].model_id,
                base=COST_SCENARIOS["base"].model_id,
                stress=COST_SCENARIOS["stress"].model_id,
            ),
        )
    except ValidationError as error:
        _exit_with_backtest_failure(
            failure_type="execution",
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


if __name__ == "__main__":
    app()
