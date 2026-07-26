"""Read-only DuckDB catalog over one immutable accepted snapshot."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

import duckdb
import pandas as pd
import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from us_intraday_lab.contracts.datasets import DatasetManifest
from us_intraday_lab.data.quality import (
    PRODUCTION_SYMBOLS,
    ExpectedGroup,
    SymbolSessionQuality,
    assess_minute_bars,
)
from us_intraday_lab.data.resample import resample_minute_bars
from us_intraday_lab.data.snapshot import DerivedBarSize, verify_snapshot
from us_intraday_lab.settings import LabPaths

_MANIFEST_SCHEMA_VERSION = "1.0.0"
_IMPORT_EVIDENCE_SCHEMA_VERSION = "1.0.0"
_DERIVED_LINEAGE_SCHEMA_VERSION = "1.0.0"
_DERIVED_BAR_SIZES: tuple[DerivedBarSize, ...] = ("5min", "15min")


class CatalogAcceptanceError(ValueError):
    """Raised when a snapshot or its read-only catalog fails acceptance."""


@dataclass(frozen=True, slots=True)
class AcceptanceSummary:
    dataset_id: str
    quality_passed: bool
    production_symbols: tuple[str, ...]
    bar_counts: dict[str, int]


def _derived_root(paths: LabPaths, dataset_id: str) -> Path:
    root = paths.canonical.parent / "derived" / dataset_id
    if root.resolve().parent != (paths.canonical.parent / "derived").resolve():
        raise CatalogAcceptanceError("dataset_id must identify one derived snapshot")
    return root


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_parquet_files(paths: LabPaths, dataset_id: str) -> tuple[Path, ...]:
    files = tuple(
        sorted(
            (paths.canonical / dataset_id).rglob("*.parquet"),
            key=lambda path: path.as_posix(),
        )
    )
    if not files:
        raise CatalogAcceptanceError("accepted snapshot contains no minute-bar Parquet files")
    return files


def _read_minute_bars(files: tuple[Path, ...]) -> pd.DataFrame:
    frames = [pd.read_parquet(path) for path in files]
    return pd.concat(frames, ignore_index=True).sort_values(
        ["symbol", "timestamp"],
        kind="stable",
        ignore_index=True,
    )


def _manifest_frame(
    manifest: DatasetManifest,
    evidence: dict[str, Any],
) -> pd.DataFrame:
    source_declaration = cast(dict[str, Any], evidence["source_declaration"])
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
                "duplicate_rows": manifest.quality.duplicate_rows,
                "missing_expected_bars": manifest.quality.missing_expected_bars,
                "invalid_ohlc_rows": manifest.quality.invalid_ohlc_rows,
                "invalid_volume_rows": manifest.quality.invalid_volume_rows,
                "outside_session_rows": manifest.quality.outside_session_rows,
                "non_monotonic_groups": manifest.quality.non_monotonic_groups,
                "import_evidence_schema_version": evidence["schema_version"],
                "source_recipe_sha256": evidence["source_recipe_sha256"],
                "declared_production_symbols": source_declaration["production_symbols"],
                "declared_robustness_groups": source_declaration["expected_robustness_groups"],
                "effective_production_symbols": evidence["effective_production_symbols"],
                "expected_start_date": date.fromisoformat(
                    str(source_declaration["expected_start_date"])
                ),
                "expected_end_date": date.fromisoformat(
                    str(source_declaration["expected_end_date"])
                ),
                "declared_ingested_at": manifest.created_at,
            }
        ]
    )


def _quality_scope(evidence: dict[str, Any]) -> tuple[set[ExpectedGroup], tuple[str, ...]]:
    raw_production = evidence["effective_production_symbols"]
    if not isinstance(raw_production, list) or not all(
        isinstance(symbol, str) for symbol in raw_production
    ):
        raise CatalogAcceptanceError("import evidence production universe is invalid")
    production_symbols = tuple(cast(list[str], raw_production))
    if tuple(sorted(set(production_symbols))) != production_symbols:
        raise CatalogAcceptanceError("import evidence production universe is not canonical")

    raw_expected = evidence["expected_production_groups"]
    if not isinstance(raw_expected, list):
        raise CatalogAcceptanceError("import evidence expected production groups are invalid")
    expected_groups: set[ExpectedGroup] = set()
    for raw_group in raw_expected:
        if not isinstance(raw_group, dict):
            raise CatalogAcceptanceError("import evidence expected production group is invalid")
        try:
            group = (
                str(raw_group["symbol"]),
                date.fromisoformat(str(raw_group["session_date"])),
            )
        except (KeyError, ValueError) as error:
            raise CatalogAcceptanceError(
                "import evidence expected production group is invalid"
            ) from error
        expected_groups.add(group)
    if len(expected_groups) != len(raw_expected):
        raise CatalogAcceptanceError("import evidence expected production groups are duplicated")
    if {symbol for symbol, _ in expected_groups}.difference(production_symbols):
        raise CatalogAcceptanceError(
            "import evidence expected groups exceed the production universe"
        )
    return expected_groups, production_symbols


def _quality_frame(bars: pd.DataFrame, evidence: dict[str, Any]) -> pd.DataFrame:
    expected_groups, production_symbols = _quality_scope(evidence)
    published_quality = assess_minute_bars(
        bars,
        expected_groups=expected_groups,
        production_symbols=production_symbols,
    )
    expected_published = {
        (group.symbol, group.session_date): group for group in published_quality.groups
    }
    raw_records = evidence.get("source_group_quality")
    if not isinstance(raw_records, list):
        raise CatalogAcceptanceError("complete source group-quality evidence is missing")
    expected_fields = {
        "symbol",
        "session_date",
        "production",
        "expected_bars",
        "observed_bars",
        "missing_expected_bars",
        "duplicate_rows",
        "invalid_ohlc_rows",
        "invalid_volume_rows",
        "outside_session_rows",
        "non_monotonic",
        "structural_passed",
        "passed",
        "requires_quarantine",
        "publication_state",
    }
    records: list[dict[str, object]] = []
    seen_groups: set[ExpectedGroup] = set()
    for raw_record in raw_records:
        if not isinstance(raw_record, dict) or set(raw_record) != expected_fields:
            raise CatalogAcceptanceError("source group-quality evidence record is invalid")
        try:
            symbol = str(raw_record["symbol"])
            session_date = date.fromisoformat(str(raw_record["session_date"]))
            group = SymbolSessionQuality(
                symbol=symbol,
                session_date=session_date,
                production=cast(bool, raw_record["production"]),
                expected_bars=cast(int, raw_record["expected_bars"]),
                observed_bars=cast(int, raw_record["observed_bars"]),
                missing_expected_bars=cast(int, raw_record["missing_expected_bars"]),
                duplicate_rows=cast(int, raw_record["duplicate_rows"]),
                invalid_ohlc_rows=cast(int, raw_record["invalid_ohlc_rows"]),
                invalid_volume_rows=cast(int, raw_record["invalid_volume_rows"]),
                outside_session_rows=cast(int, raw_record["outside_session_rows"]),
                non_monotonic=cast(bool, raw_record["non_monotonic"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise CatalogAcceptanceError(
                "source group-quality evidence record is invalid"
            ) from error
        key = (symbol, session_date)
        if key in seen_groups:
            raise CatalogAcceptanceError("source group-quality evidence groups are duplicated")
        seen_groups.add(key)
        state = raw_record["publication_state"]
        if state not in {"published", "quarantined"}:
            raise CatalogAcceptanceError("source group-quality publication state is invalid")
        if (
            raw_record["structural_passed"] is not group.structural_passed
            or raw_record["passed"] is not group.passed
            or raw_record["requires_quarantine"] is not group.requires_quarantine
            or (state == "quarantined") is not group.requires_quarantine
        ):
            raise CatalogAcceptanceError("source group-quality evidence semantics are invalid")
        if state == "published":
            recomputed = expected_published.get(key)
            if recomputed is None or asdict(recomputed) != asdict(group):
                raise CatalogAcceptanceError(
                    "published source group quality is not reproducible from canonical bars"
                )
        elif key in expected_published and expected_published[key].observed_bars:
            raise CatalogAcceptanceError(
                "quarantined source group unexpectedly exists in canonical bars"
            )
        records.append(
            {
                **asdict(group),
                "structural_passed": group.structural_passed,
                "passed": group.passed,
                "requires_quarantine": group.requires_quarantine,
                "publication_state": state,
            }
        )
    published_keys = {
        key
        for key, group in expected_published.items()
        if group.observed_bars > 0 or group.production
    }
    evidence_published_keys = {
        (cast(str, record["symbol"]), cast(date, record["session_date"]))
        for record in records
        if record["publication_state"] == "published"
    }
    if published_keys != evidence_published_keys:
        raise CatalogAcceptanceError(
            "source group-quality publication state does not match canonical bars"
        )
    return pd.DataFrame(records).sort_values(
        ["symbol", "session_date"],
        kind="stable",
        ignore_index=True,
    )


def _write_derived_artifacts(
    target: Path,
    *,
    manifest: DatasetManifest,
    bars: pd.DataFrame,
    evidence: dict[str, Any],
) -> None:
    artifacts: dict[str, dict[str, object]] = {}
    for bar_size in _DERIVED_BAR_SIZES:
        derived = resample_minute_bars(
            bars,
            bar_size=bar_size,
            parent_snapshot_id=manifest.dataset_id,
        )
        output = target / f"bar_size={bar_size}" / "part-00000.parquet"
        output.parent.mkdir(parents=True)
        derived.to_parquet(output, index=False)
        artifacts[f"bars_{bar_size}"] = {
            "relative_path": output.relative_to(target).as_posix(),
            "sha256": _sha256_file(output),
            "row_count": len(derived),
            "bar_size": bar_size,
            "source_bar_size": "1min",
            "parent_snapshot_id": manifest.dataset_id,
        }

    metadata = {
        "dataset_manifests": _manifest_frame(manifest, evidence),
        "symbol_session_quality": _quality_frame(bars, evidence),
    }
    for name, frame in metadata.items():
        output = target / "metadata" / f"{name}.parquet"
        output.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(output, index=False)
        artifacts[name] = {
            "relative_path": output.relative_to(target).as_posix(),
            "sha256": _sha256_file(output),
            "row_count": len(frame),
        }

    lineage = {
        "schema_version": _DERIVED_LINEAGE_SCHEMA_VERSION,
        "parent_snapshot_id": manifest.dataset_id,
        "parent_content_sha256": manifest.content_sha256,
        "artifacts": artifacts,
    }
    (target / "lineage.json").write_text(
        json.dumps(lineage, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _load_lineage(derived_root: Path) -> dict[str, Any]:
    lineage_path = derived_root / "lineage.json"
    if not lineage_path.is_file():
        raise CatalogAcceptanceError("derived lineage manifest does not exist")
    try:
        return cast(
            dict[str, Any],
            json.loads(lineage_path.read_text(encoding="utf-8")),
        )
    except (json.JSONDecodeError, OSError) as error:
        raise CatalogAcceptanceError("derived lineage manifest is unreadable") from error


def _verified_artifact_paths(
    derived_root: Path,
    *,
    manifest: DatasetManifest,
) -> dict[str, Path]:
    lineage = _load_lineage(derived_root)
    if set(lineage) != {
        "schema_version",
        "parent_snapshot_id",
        "parent_content_sha256",
        "artifacts",
    }:
        raise CatalogAcceptanceError("derived lineage fields do not match the required schema")
    if lineage.get("schema_version") != _DERIVED_LINEAGE_SCHEMA_VERSION:
        raise CatalogAcceptanceError("unsupported derived lineage schema version")
    if lineage.get("parent_snapshot_id") != manifest.dataset_id:
        raise CatalogAcceptanceError("derived lineage parent snapshot does not match")
    if lineage.get("parent_content_sha256") != manifest.content_sha256:
        raise CatalogAcceptanceError("derived lineage parent content hash does not match")
    raw_artifacts = lineage.get("artifacts")
    if not isinstance(raw_artifacts, dict):
        raise CatalogAcceptanceError("derived lineage artifacts are missing")

    required = {
        "bars_5min",
        "bars_15min",
        "dataset_manifests",
        "symbol_session_quality",
    }
    if set(raw_artifacts) != required:
        raise CatalogAcceptanceError("derived lineage artifacts do not match the required set")

    expected_records: dict[str, tuple[str, dict[str, object]]] = {
        "bars_5min": (
            "bar_size=5min/part-00000.parquet",
            {
                "bar_size": "5min",
                "source_bar_size": "1min",
                "parent_snapshot_id": manifest.dataset_id,
            },
        ),
        "bars_15min": (
            "bar_size=15min/part-00000.parquet",
            {
                "bar_size": "15min",
                "source_bar_size": "1min",
                "parent_snapshot_id": manifest.dataset_id,
            },
        ),
        "dataset_manifests": (
            "metadata/dataset_manifests.parquet",
            {},
        ),
        "symbol_session_quality": (
            "metadata/symbol_session_quality.parquet",
            {},
        ),
    }
    paths: dict[str, Path] = {}
    for name in sorted(required):
        record = raw_artifacts[name]
        if not isinstance(record, dict):
            raise CatalogAcceptanceError(f"derived artifact record is invalid: {name}")
        expected_path, expected_metadata = expected_records[name]
        expected_fields = {"relative_path", "sha256", "row_count", *expected_metadata}
        if set(record) != expected_fields:
            raise CatalogAcceptanceError(f"derived artifact lineage fields are invalid: {name}")
        relative_path = record.get("relative_path")
        if relative_path != expected_path:
            raise CatalogAcceptanceError(f"derived artifact path is invalid: {name}")
        for field_name, expected_value in expected_metadata.items():
            if record.get(field_name) != expected_value:
                raise CatalogAcceptanceError(
                    f"derived artifact lineage {field_name} is invalid: {name}"
                )
        if type(record.get("row_count")) is not int or record["row_count"] < 0:
            raise CatalogAcceptanceError(f"derived artifact row count is invalid: {name}")
        recorded_sha = record.get("sha256")
        if (
            not isinstance(recorded_sha, str)
            or len(recorded_sha) != 64
            or any(character not in "0123456789abcdef" for character in recorded_sha)
        ):
            raise CatalogAcceptanceError(f"derived artifact hash is invalid: {name}")
        path = (derived_root / relative_path).resolve()
        if not path.is_relative_to(derived_root.resolve()) or not path.is_file():
            raise CatalogAcceptanceError(f"derived artifact is missing: {name}")
        if _sha256_file(path) != record.get("sha256"):
            raise CatalogAcceptanceError(f"derived artifact hash mismatch: {name}")
        paths[name] = path
    return paths


def _publish_derived_snapshot(
    paths: LabPaths,
    *,
    manifest: DatasetManifest,
    bars: pd.DataFrame,
    evidence: dict[str, Any],
) -> dict[str, Path]:
    final_root = _derived_root(paths, manifest.dataset_id)
    if final_root.exists():
        return _verified_artifact_paths(final_root, manifest=manifest)

    parent = final_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".derived-", dir=parent)).resolve()
    try:
        _write_derived_artifacts(
            temporary,
            manifest=manifest,
            bars=bars,
            evidence=evidence,
        )
        temporary.rename(final_root)
    except BaseException:
        if temporary.exists() and temporary.parent == parent.resolve():
            shutil.rmtree(temporary)
        raise
    return _verified_artifact_paths(final_root, manifest=manifest)


def _sql_string(path: Path) -> str:
    return "'" + path.resolve().as_posix().replace("'", "''") + "'"


def _parquet_source(files: tuple[Path, ...]) -> str:
    explicit_paths = ", ".join(_sql_string(path) for path in files)
    return f"read_parquet([{explicit_paths}], hive_partitioning = false, union_by_name = true)"


def _catalog_sources(
    *,
    minute_files: tuple[Path, ...],
    artifacts: dict[str, Path],
) -> dict[str, str]:
    return {
        "bars_1m": _parquet_source(minute_files),
        "bars_5m": _parquet_source((artifacts["bars_5min"],)),
        "bars_15m": _parquet_source((artifacts["bars_15min"],)),
        "dataset_manifests": _parquet_source((artifacts["dataset_manifests"],)),
        "symbol_session_quality": _parquet_source((artifacts["symbol_session_quality"],)),
    }


def _view_definitions(connection: duckdb.DuckDBPyConnection) -> dict[str, str]:
    return dict(
        connection.execute(
            """
            SELECT view_name, sql
            FROM duckdb_views()
            WHERE database_name = current_database()
              AND schema_name = 'main'
            ORDER BY view_name
            """
        ).fetchall()
    )


def _expected_view_definitions(sources: dict[str, str]) -> dict[str, str]:
    with duckdb.connect() as connection:
        for view_name, source in sources.items():
            connection.execute(f"CREATE VIEW {view_name} AS SELECT * FROM {source}")
        return _view_definitions(connection)


def _create_catalog(
    catalog_path: Path,
    *,
    minute_files: tuple[Path, ...],
    artifacts: dict[str, Path],
) -> None:
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = catalog_path.parent / f".{catalog_path.name}.{os.getpid()}.tmp"
    if temporary.exists():
        temporary.unlink()
    try:
        with duckdb.connect(str(temporary)) as connection:
            sources = _catalog_sources(minute_files=minute_files, artifacts=artifacts)
            for view_name, source in sources.items():
                connection.execute(f"CREATE VIEW {view_name} AS SELECT * FROM {source}")
        os.replace(temporary, catalog_path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _verified_import_evidence(
    paths: LabPaths,
    manifest: DatasetManifest,
) -> dict[str, Any]:
    if manifest.schema_version != _MANIFEST_SCHEMA_VERSION:
        raise CatalogAcceptanceError(
            f"unsupported snapshot manifest schema version: {manifest.schema_version}"
        )
    evidence_path = paths.canonical / manifest.dataset_id / "import-evidence.json"
    try:
        evidence = cast(
            dict[str, Any],
            json.loads(evidence_path.read_text(encoding="utf-8")),
        )
    except (FileNotFoundError, json.JSONDecodeError, OSError) as error:
        raise CatalogAcceptanceError("snapshot import evidence is unreadable") from error
    if evidence.get("schema_version") != _IMPORT_EVIDENCE_SCHEMA_VERSION:
        raise CatalogAcceptanceError("unsupported import evidence schema version")
    if evidence.get("source_sha256") != manifest.source_sha256:
        raise CatalogAcceptanceError("import evidence source hash does not match manifest")
    _quality_scope(evidence)
    return evidence


def _verify_metadata_content(
    artifacts: dict[str, Path],
    *,
    manifest: DatasetManifest,
    minute_bars: pd.DataFrame,
    evidence: dict[str, Any],
) -> dict[str, int]:
    expected_frames = {
        "dataset_manifests": _manifest_frame(manifest, evidence),
        "symbol_session_quality": _quality_frame(minute_bars, evidence),
    }
    counts: dict[str, int] = {}
    for name, expected_frame in expected_frames.items():
        expected_sink = pa.BufferOutputStream()
        pq.write_table(
            pa.Table.from_pandas(expected_frame, preserve_index=False),
            expected_sink,
        )
        expected = pq.ParquetFile(pa.BufferReader(expected_sink.getvalue())).read()
        actual = pq.ParquetFile(artifacts[name]).read()
        if not actual.schema.equals(expected.schema, check_metadata=True) or not actual.equals(
            expected
        ):
            raise CatalogAcceptanceError(
                f"{name} metadata is not reproducible from the canonical snapshot"
            )
        counts[name] = len(expected_frame)
    return counts


def _verify_lineage_row_counts(
    derived_root: Path,
    expected_counts: dict[str, int],
) -> None:
    artifacts = cast(dict[str, Any], _load_lineage(derived_root)["artifacts"])
    for name, expected_count in expected_counts.items():
        record = cast(dict[str, Any], artifacts[name])
        if record["row_count"] != expected_count:
            raise CatalogAcceptanceError(f"derived artifact lineage row count is invalid: {name}")


def _verify_derived_content(
    artifacts: dict[str, Path],
    *,
    minute_bars: pd.DataFrame,
    dataset_id: str,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for bar_size in _DERIVED_BAR_SIZES:
        frame = pd.read_parquet(artifacts[f"bars_{bar_size}"])
        if frame.empty:
            raise CatalogAcceptanceError(f"derived {bar_size} bars are empty")
        if set(frame["parent_snapshot_id"].astype(str)) != {dataset_id}:
            raise CatalogAcceptanceError(f"derived {bar_size} parent lineage does not match")
        if set(frame["source_bar_size"].astype(str)) != {"1min"}:
            raise CatalogAcceptanceError(f"derived {bar_size} source lineage does not match")
        if set(frame["bar_size"].astype(str)) != {bar_size}:
            raise CatalogAcceptanceError(f"derived {bar_size} bar-size lineage does not match")
        expected = resample_minute_bars(
            minute_bars,
            bar_size=bar_size,
            parent_snapshot_id=dataset_id,
        )
        try:
            pd.testing.assert_frame_equal(
                frame.reset_index(drop=True),
                expected.reset_index(drop=True),
                check_exact=True,
            )
        except AssertionError as error:
            raise CatalogAcceptanceError(
                f"derived {bar_size} content is not reproducible from parent snapshot"
            ) from error
        counts[bar_size] = len(expected)
    return counts


def build_catalog(dataset_id: str, *, root: Path) -> Path:
    """Build a DuckDB file containing views only, bound to explicit Parquet paths."""
    paths = LabPaths.from_root(root)
    manifest = verify_snapshot(dataset_id, root=paths.root)
    evidence = _verified_import_evidence(paths, manifest)
    minute_files = _snapshot_parquet_files(paths, dataset_id)
    bars = _read_minute_bars(minute_files)
    artifacts = _publish_derived_snapshot(
        paths,
        manifest=manifest,
        bars=bars,
        evidence=evidence,
    )
    derived_counts = _verify_derived_content(
        artifacts,
        minute_bars=bars,
        dataset_id=dataset_id,
    )
    metadata_counts = _verify_metadata_content(
        artifacts,
        manifest=manifest,
        minute_bars=bars,
        evidence=evidence,
    )
    _verify_lineage_row_counts(
        _derived_root(paths, dataset_id),
        {**{f"bars_{key}": value for key, value in derived_counts.items()}, **metadata_counts},
    )
    _create_catalog(
        paths.catalog,
        minute_files=minute_files,
        artifacts=artifacts,
    )
    return paths.catalog


def connect_catalog(*, root: Path) -> duckdb.DuckDBPyConnection:
    """Open the application catalog with DuckDB's enforced read-only mode."""
    catalog_path = LabPaths.from_root(root).catalog
    if not catalog_path.is_file():
        raise FileNotFoundError(f"catalog does not exist: {catalog_path}")
    return duckdb.connect(str(catalog_path), read_only=True)


def _catalog_bar_counts(connection: duckdb.DuckDBPyConnection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for bar_size, view in {
        "1min": "bars_1m",
        "5min": "bars_5m",
        "15min": "bars_15m",
    }.items():
        row = connection.execute(f"SELECT count(*) FROM {view}").fetchone()
        if row is None:
            raise CatalogAcceptanceError(f"catalog count query returned no row: {view}")
        counts[bar_size] = cast(int, row[0])
    return counts


def _verify_catalog_objects_and_bindings(
    connection: duckdb.DuckDBPyConnection,
    *,
    minute_files: tuple[Path, ...],
    artifacts: dict[str, Path],
) -> None:
    sources = _catalog_sources(minute_files=minute_files, artifacts=artifacts)
    expected_definitions = _expected_view_definitions(sources)
    actual_definitions = _view_definitions(connection)
    user_table_row = connection.execute(
        """
        SELECT count(*)
        FROM duckdb_tables()
        WHERE database_name = current_database()
          AND schema_name = 'main'
        """
    ).fetchone()
    if user_table_row is None:
        raise CatalogAcceptanceError("catalog object inspection returned no result")
    user_table_count = cast(int, user_table_row[0])
    if set(actual_definitions) != set(sources) or user_table_count != 0:
        raise CatalogAcceptanceError(
            "catalog objects must contain exactly five expected views and zero user tables"
        )
    if actual_definitions != expected_definitions:
        raise CatalogAcceptanceError(
            "catalog view bindings and definitions do not match verified artifacts"
        )


def _verify_catalog_content(
    connection: duckdb.DuckDBPyConnection,
    expected_frames: dict[str, pd.DataFrame],
) -> None:
    for view_name, expected_frame in expected_frames.items():
        registered_name = f"_expected_{view_name}"
        connection.register(
            registered_name,
            pa.Table.from_pandas(expected_frame, preserve_index=False),
        )
        try:
            difference = connection.execute(
                f"""
                SELECT count(*)
                FROM (
                    (SELECT * FROM {view_name}
                     EXCEPT ALL
                     SELECT * FROM {registered_name})
                    UNION ALL
                    (SELECT * FROM {registered_name}
                     EXCEPT ALL
                     SELECT * FROM {view_name})
                )
                """
            ).fetchone()
        finally:
            connection.unregister(registered_name)
        if difference is None or difference[0] != 0:
            raise CatalogAcceptanceError(
                f"catalog view content does not exactly match verified artifacts: {view_name}"
            )


def accept_dataset(dataset_id: str, *, root: Path) -> AcceptanceSummary:
    """Verify immutable inputs, derived lineage, coverage, and read-only queries."""
    paths = LabPaths.from_root(root)
    try:
        manifest = verify_snapshot(dataset_id, root=paths.root)
    except (ValueError, OSError) as error:
        raise CatalogAcceptanceError(f"snapshot verification failed: {error}") from error
    evidence = _verified_import_evidence(paths, manifest)
    artifacts = _verified_artifact_paths(
        _derived_root(paths, dataset_id),
        manifest=manifest,
    )
    required_production = tuple(sorted(PRODUCTION_SYMBOLS))
    missing = sorted(set(required_production).difference(manifest.symbols))
    if missing:
        raise CatalogAcceptanceError(
            "production-symbol coverage requires IWM,QQQ,SPY; missing " + ",".join(missing)
        )

    minute_files = _snapshot_parquet_files(paths, dataset_id)
    minute_bars = _read_minute_bars(minute_files)
    expected_counts = {"1min": manifest.row_count}
    derived_counts = _verify_derived_content(
        artifacts,
        minute_bars=minute_bars,
        dataset_id=dataset_id,
    )
    metadata_counts = _verify_metadata_content(
        artifacts,
        manifest=manifest,
        minute_bars=minute_bars,
        evidence=evidence,
    )
    _verify_lineage_row_counts(
        _derived_root(paths, dataset_id),
        {**{f"bars_{key}": value for key, value in derived_counts.items()}, **metadata_counts},
    )
    expected_counts.update(derived_counts)
    expected_frames = {
        "bars_1m": minute_bars,
        "bars_5m": resample_minute_bars(
            minute_bars,
            bar_size="5min",
            parent_snapshot_id=dataset_id,
        ),
        "bars_15m": resample_minute_bars(
            minute_bars,
            bar_size="15min",
            parent_snapshot_id=dataset_id,
        ),
        "dataset_manifests": _manifest_frame(manifest, evidence),
        "symbol_session_quality": _quality_frame(minute_bars, evidence),
    }

    try:
        with connect_catalog(root=paths.root) as connection:
            access_mode = connection.execute(
                "SELECT lower(current_setting('access_mode'))"
            ).fetchone()
            if access_mode != ("read_only",):
                raise CatalogAcceptanceError("application catalog connection is not read-only")
            _verify_catalog_objects_and_bindings(
                connection,
                minute_files=minute_files,
                artifacts=artifacts,
            )
            _verify_catalog_content(connection, expected_frames)
            selected_dataset = connection.execute(
                "SELECT dataset_id, quality_passed FROM dataset_manifests"
            ).fetchall()
            if selected_dataset != [(dataset_id, True)]:
                raise CatalogAcceptanceError(
                    "catalog manifest view does not match accepted dataset"
                )
            passed_production = {
                row[0]
                for row in connection.execute(
                    """
                    SELECT symbol
                    FROM symbol_session_quality
                    WHERE production AND passed
                    """
                ).fetchall()
            }
            if passed_production != set(required_production):
                raise CatalogAcceptanceError(
                    "catalog production symbol/session quality does not pass"
                )
            failed_production = connection.execute(
                """
                SELECT count(*)
                FROM symbol_session_quality
                WHERE production AND NOT passed
                """
            ).fetchone()
            if failed_production is None or failed_production[0] != 0:
                raise CatalogAcceptanceError(
                    "catalog contains failed production symbol/session quality"
                )
            bar_counts = _catalog_bar_counts(connection)
    except CatalogAcceptanceError:
        raise
    except (duckdb.Error, OSError) as error:
        raise CatalogAcceptanceError(f"read-only catalog query failed: {error}") from error

    if bar_counts != expected_counts:
        raise CatalogAcceptanceError("catalog bar counts do not match immutable artifacts")
    return AcceptanceSummary(
        dataset_id=dataset_id,
        quality_passed=manifest.quality.passed,
        production_symbols=required_production,
        bar_counts=bar_counts,
    )
