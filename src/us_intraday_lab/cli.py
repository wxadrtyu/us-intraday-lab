from pathlib import Path
from typing import Annotated

import typer

from us_intraday_lab.data.archive import inspect_archive
from us_intraday_lab.data.snapshot import import_snapshot, verify_snapshot

app = typer.Typer(no_args_is_help=True)
data_app = typer.Typer(no_args_is_help=True)
app.add_typer(data_app, name="data")


@data_app.command("inspect-archive")
def inspect_archive_command(
    archive: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, readable=True)
    ],
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
    archive: Annotated[
        Path, typer.Option(exists=True, dir_okay=False, readable=True)
    ],
    root: Annotated[Path, typer.Option(file_okay=False)],
) -> None:
    manifest, _ = import_snapshot(archive, root=root)
    typer.echo(manifest.dataset_id)


@data_app.command("verify-snapshot")
def verify_snapshot_command(
    dataset_id: Annotated[str, typer.Option()],
    root: Annotated[Path, typer.Option(exists=True, file_okay=False, readable=True)],
) -> None:
    manifest = verify_snapshot(dataset_id, root=root)
    typer.echo(manifest.dataset_id)
