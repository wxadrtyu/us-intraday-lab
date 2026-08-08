from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import duckdb
import pandas as pd

from us_intraday_lab.long_horizon.snapshot import (
    read_five_minute_snapshot,
    verify_five_minute_snapshot,
)

_SYMBOLS = ("AAPL", "QQQ")


class FiveMinuteCatalogAcceptanceError(ValueError):
    """Raised when the long-horizon read-only catalog fails acceptance."""


@dataclass(frozen=True, slots=True)
class FiveMinuteAcceptanceSummary:
    dataset_id: str
    accepted_sessions: int
    symbols: tuple[str, ...]
    missing_expected_bars: int
    row_count: int


def _snapshot_root(root: Path, dataset_id: str) -> Path:
    return (
        root.resolve()
        / "data"
        / "lake"
        / "long_horizon"
        / "canonical"
        / dataset_id
    )


def _catalog_path(root: Path, dataset_id: str) -> Path:
    parent = root.resolve() / "data" / "catalog" / "long_horizon"
    candidate = parent / f"{dataset_id}.duckdb"
    if candidate.resolve().parent != parent.resolve():
        raise FiveMinuteCatalogAcceptanceError("dataset_id must identify one catalog")
    return candidate


def _manifest_artifact(root: Path, dataset_id: str) -> Path:
    return (
        root.resolve()
        / "data"
        / "lake"
        / "long_horizon"
        / "catalog_artifacts"
        / dataset_id
        / "dataset_manifests.parquet"
    )


def _sql_path(path: Path) -> str:
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def _parquet_source(paths: tuple[Path, ...]) -> str:
    values = ", ".join(_sql_path(path) for path in paths)
    return f"read_parquet([{values}], hive_partitioning = false, union_by_name = true)"


def _manifest_frame(dataset_id: str, *, root: Path) -> pd.DataFrame:
    manifest = verify_five_minute_snapshot(dataset_id, root=root)
    return pd.DataFrame(
        [
            {
                "dataset_id": manifest.dataset_id,
                "schema_version": manifest.schema_version,
                "source_uri": manifest.source_uri,
                "source_sha256": manifest.source_sha256,
                "content_sha256": manifest.content_sha256,
                "code_revision": manifest.code_revision,
                "calendar_name": manifest.calendar_name,
                "calendar_version": manifest.calendar_version,
                "created_at": manifest.created_at,
                "provider": manifest.provider,
                "feed": manifest.feed,
                "bar_size": manifest.bar_size,
                "row_count": manifest.row_count,
                "symbols": list(manifest.symbols),
                "min_timestamp": manifest.min_timestamp,
                "max_timestamp": manifest.max_timestamp,
                "quality_passed": manifest.quality.passed,
            }
        ]
    )


def _sources(dataset_id: str, *, root: Path) -> dict[str, str]:
    snapshot = _snapshot_root(root, dataset_id)
    bar_files = tuple(sorted(snapshot.glob("bar_size=5min/session_date=*/symbol=*/part-00000.parquet")))
    if not bar_files:
        raise FiveMinuteCatalogAcceptanceError("verified snapshot contains no bar partitions")
    quality = snapshot / "metadata" / "symbol_session_quality.parquet"
    manifest = _manifest_artifact(root, dataset_id)
    if not quality.is_file() or not manifest.is_file():
        raise FiveMinuteCatalogAcceptanceError("catalog metadata artifacts are missing")
    return {
        "bars_5m": _parquet_source(bar_files),
        "dataset_manifests": _parquet_source((manifest,)),
        "symbol_session_quality": _parquet_source((quality,)),
    }


def build_five_minute_catalog(dataset_id: str, *, root: Path) -> Path:
    """Build an isolated DuckDB catalog containing only explicit Parquet views."""

    verify_five_minute_snapshot(dataset_id, root=root)
    manifest_artifact = _manifest_artifact(root, dataset_id)
    manifest_artifact.parent.mkdir(parents=True, exist_ok=True)
    _manifest_frame(dataset_id, root=root).to_parquet(manifest_artifact, index=False)
    catalog_path = _catalog_path(root, dataset_id)
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = catalog_path.parent / f".{catalog_path.name}.{os.getpid()}.tmp"
    try:
        if temporary.exists():
            temporary.unlink()
        with duckdb.connect(str(temporary)) as connection:
            for view_name, source in _sources(dataset_id, root=root).items():
                connection.execute(f"CREATE VIEW {view_name} AS SELECT * FROM {source}")
        os.replace(temporary, catalog_path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return catalog_path


def connect_five_minute_catalog(
    dataset_id: str,
    *,
    root: Path,
) -> duckdb.DuckDBPyConnection:
    """Open one long-horizon dataset catalog in enforced read-only mode."""

    path = _catalog_path(root, dataset_id)
    if not path.is_file():
        raise FileNotFoundError(f"five-minute catalog does not exist: {path}")
    return duckdb.connect(str(path), read_only=True)


def accept_five_minute_dataset(
    dataset_id: str,
    *,
    root: Path,
) -> FiveMinuteAcceptanceSummary:
    """Accept only the exact shared complete AAPL/QQQ session intersection."""

    manifest = verify_five_minute_snapshot(dataset_id, root=root)
    expected_bars = read_five_minute_snapshot(dataset_id, root=root)
    if tuple(manifest.symbols) != _SYMBOLS:
        raise FiveMinuteCatalogAcceptanceError("dataset symbol scope must be AAPL, QQQ")
    try:
        with connect_five_minute_catalog(dataset_id, root=root) as connection:
            if connection.execute(
                "SELECT lower(current_setting('access_mode'))"
            ).fetchone() != ("read_only",):
                raise FiveMinuteCatalogAcceptanceError("catalog is not read-only")
            objects = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT view_name FROM duckdb_views()
                    WHERE database_name = current_database() AND schema_name = 'main'
                    """
                ).fetchall()
            }
            table_count = connection.execute(
                """
                SELECT count(*) FROM duckdb_tables()
                WHERE database_name = current_database() AND schema_name = 'main'
                """
            ).fetchone()
            if objects != {"bars_5m", "dataset_manifests", "symbol_session_quality"} or table_count != (0,):
                raise FiveMinuteCatalogAcceptanceError("catalog object scope is invalid")
            catalog_bars = connection.execute(
                "SELECT * FROM bars_5m ORDER BY session_date, timestamp, symbol"
            ).fetchdf()
            catalog_bars["session_date"] = pd.to_datetime(
                catalog_bars["session_date"]
            ).dt.date
            try:
                pd.testing.assert_frame_equal(
                    catalog_bars.reset_index(drop=True),
                    expected_bars.reset_index(drop=True),
                    check_dtype=False,
                    check_exact=True,
                )
            except AssertionError as error:
                raise FiveMinuteCatalogAcceptanceError(
                    "catalog bars do not match the verified snapshot"
                ) from error
            rejected_in_bars = connection.execute(
                """
                SELECT count(*)
                FROM bars_5m AS bars
                JOIN symbol_session_quality AS quality
                  USING (symbol, session_date)
                WHERE quality.publication_state <> 'accepted' OR NOT quality.passed
                """
            ).fetchone()
            if rejected_in_bars != (0,):
                raise FiveMinuteCatalogAcceptanceError("catalog exposes rejected sessions")
            accepted_sessions_row = connection.execute(
                """
                SELECT count(*) FROM (
                    SELECT session_date
                    FROM symbol_session_quality
                    WHERE publication_state = 'accepted' AND passed
                    GROUP BY session_date
                    HAVING count(DISTINCT symbol) = 2
                )
                """
            ).fetchone()
            missing_row = connection.execute(
                """
                SELECT coalesce(sum(missing_expected_bars), 0)
                FROM symbol_session_quality
                WHERE publication_state = 'accepted'
                """
            ).fetchone()
            symbols = tuple(
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT symbol FROM bars_5m ORDER BY symbol"
                ).fetchall()
            )
    except FiveMinuteCatalogAcceptanceError:
        raise
    except (duckdb.Error, OSError) as error:
        raise FiveMinuteCatalogAcceptanceError(f"catalog verification failed: {error}") from error
    if accepted_sessions_row is None or missing_row is None:
        raise FiveMinuteCatalogAcceptanceError("catalog aggregate query returned no row")
    accepted_sessions = cast(int, accepted_sessions_row[0])
    missing_expected_bars = cast(int, missing_row[0])
    if symbols != _SYMBOLS or accepted_sessions <= 0 or missing_expected_bars != 0:
        raise FiveMinuteCatalogAcceptanceError("shared complete-session gate failed")
    return FiveMinuteAcceptanceSummary(
        dataset_id=dataset_id,
        accepted_sessions=accepted_sessions,
        symbols=symbols,
        missing_expected_bars=missing_expected_bars,
        row_count=len(expected_bars),
    )
