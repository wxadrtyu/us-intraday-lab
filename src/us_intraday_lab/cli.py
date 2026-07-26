from datetime import date
from pathlib import Path
from typing import Annotated

import typer

from us_intraday_lab.data.archive import inspect_archive
from us_intraday_lab.data.catalog import accept_dataset, build_catalog
from us_intraday_lab.data.snapshot import (
    ArchiveSourceDeclaration,
    import_snapshot,
    verify_snapshot,
)

app = typer.Typer(no_args_is_help=True)
data_app = typer.Typer(no_args_is_help=True)
app.add_typer(data_app, name="data")


@data_app.command("inspect-archive")
def inspect_archive_command(
    archive: Annotated[Path, typer.Option(exists=True, dir_okay=False, readable=True)],
) -> None:
    inspection = inspect_archive(archive)
    typer.echo(f"archive: {inspection.archive}")
    typer.echo(f"source_sha256: {inspection.source_sha256}")
    for member in inspection.members:
        typer.echo(f"member: {member.name}")
        typer.echo(f"  size_bytes: {member.size}")
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
) -> None:
    source = ArchiveSourceDeclaration(
        provider=provider,
        feed=feed,
        bar_size=bar_size,
        member_names=tuple(member),
        production_symbols=tuple(production_symbol),
        expected_start_date=date.fromisoformat(expected_start_date),
        expected_end_date=date.fromisoformat(expected_end_date),
    )
    manifest, _ = import_snapshot(archive, root=root, source=source)
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
