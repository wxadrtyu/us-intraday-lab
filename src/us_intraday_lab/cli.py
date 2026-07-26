from datetime import date, datetime
from pathlib import Path
from typing import Annotated

import typer

from us_intraday_lab.data.archive import (
    DEFAULT_ARCHIVE_READ_LIMITS,
    ArchiveReadLimits,
    inspect_archive,
)
from us_intraday_lab.data.catalog import accept_dataset, build_catalog
from us_intraday_lab.data.snapshot import (
    ArchiveSourceDeclaration,
    import_snapshot,
    verify_snapshot,
)

app = typer.Typer(no_args_is_help=True)
data_app = typer.Typer(no_args_is_help=True)
app.add_typer(data_app, name="data")


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
