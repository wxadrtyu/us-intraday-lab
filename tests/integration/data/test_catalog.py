from __future__ import annotations

import hashlib
import importlib
import io
import json
import tarfile
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pytest
from typer.testing import CliRunner

from us_intraday_lab.cli import app
from us_intraday_lab.data.snapshot import ArchiveSourceDeclaration, import_snapshot

RUNNER = CliRunner()
MEMBER_NAME = "synthetic/minute_bars.csv"
PRODUCTION_SYMBOLS = ("IWM", "QQQ", "SPY")


def _synthetic_archive(tmp_path: Path, symbols: tuple[str, ...]) -> Path:
    timestamps = pd.date_range(
        "2026-07-02T13:30:00Z",
        periods=390,
        freq="min",
        tz="UTC",
    )
    rows: list[pd.DataFrame] = []
    for symbol_number, symbol in enumerate(symbols):
        base = 100.0 + symbol_number * 10
        offsets = pd.Series(range(len(timestamps)), dtype="float64") / 100
        rows.append(
            pd.DataFrame(
                {
                    "ticker": symbol,
                    "date": timestamps,
                    "open": base + offsets,
                    "high": base + offsets + 0.2,
                    "low": base + offsets - 0.2,
                    "close": base + offsets + 0.1,
                    "volume": 1_000 + offsets * 100,
                }
            )
        )
    payload = pd.concat(rows, ignore_index=True).to_csv(index=False).encode()
    archive_path = tmp_path / "synthetic.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        info = tarfile.TarInfo(MEMBER_NAME)
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return archive_path


def _snapshot(
    tmp_path: Path,
    *,
    symbols: tuple[str, ...] = PRODUCTION_SYMBOLS,
    production_symbols: tuple[str, ...] = PRODUCTION_SYMBOLS,
) -> tuple[Path, str]:
    root = tmp_path / "repo"
    archive = _synthetic_archive(tmp_path, symbols)
    manifest, _ = import_snapshot(
        archive,
        root=root,
        source=ArchiveSourceDeclaration(
            provider="tiingo",
            feed="iex",
            bar_size="1min",
            member_names=(MEMBER_NAME,),
            production_symbols=production_symbols,
            expected_start_date=date(2026, 7, 2),
            expected_end_date=date(2026, 7, 2),
        ),
    )
    return root, manifest.dataset_id


def _catalog_module() -> object:
    return importlib.import_module("us_intraday_lab.data.catalog")


def _artifact_path(root: Path, dataset_id: str, name: str) -> Path:
    lineage_path = root / "data" / "lake" / "derived" / dataset_id / "lineage.json"
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    return lineage_path.parent / lineage["artifacts"][name]["relative_path"]


def _rehash_artifact(root: Path, dataset_id: str, name: str) -> None:
    lineage_path = root / "data" / "lake" / "derived" / dataset_id / "lineage.json"
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    artifact = lineage_path.parent / lineage["artifacts"][name]["relative_path"]
    lineage["artifacts"][name]["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    lineage_path.write_text(json.dumps(lineage), encoding="utf-8")


def test_catalog_exposes_snapshot_and_derived_bars_as_read_only_views(
    tmp_path: Path,
) -> None:
    root, dataset_id = _snapshot(tmp_path)
    catalog = _catalog_module()

    catalog_path = catalog.build_catalog(dataset_id, root=root)

    assert catalog_path == root / "data" / "catalog" / "research.duckdb"
    with catalog.connect_catalog(root=root) as connection:
        assert connection.execute("SELECT lower(current_setting('access_mode'))").fetchone() == (
            "read_only",
        )
        assert connection.execute("SELECT count(*) FROM bars_1m").fetchone() == (1_170,)
        assert connection.execute("SELECT count(*) FROM bars_5m").fetchone() == (234,)
        assert connection.execute("SELECT count(*) FROM bars_15m").fetchone() == (78,)
        assert connection.execute(
            "SELECT dataset_id, quality_passed FROM dataset_manifests"
        ).fetchall() == [(dataset_id, True)]
        assert connection.execute(
            """
            SELECT symbol, production, passed
            FROM symbol_session_quality
            ORDER BY symbol
            """
        ).fetchall() == [
            ("IWM", True, True),
            ("QQQ", True, True),
            ("SPY", True, True),
        ]
        assert connection.execute(
            """
            SELECT count(*)
            FROM duckdb_tables()
            WHERE database_name <> 'system'
            """
        ).fetchone() == (0,)
        with pytest.raises(duckdb.Error, match="read-only|read only|READ_ONLY"):
            connection.execute("CREATE TABLE forbidden_insert (value INTEGER)")
        with pytest.raises(duckdb.Error):
            connection.execute("INSERT INTO dataset_manifests SELECT * FROM dataset_manifests")


def test_catalog_definitions_are_exactly_five_explicit_parquet_views(tmp_path: Path) -> None:
    root, dataset_id = _snapshot(tmp_path)
    catalog = _catalog_module()
    catalog.build_catalog(dataset_id, root=root)
    canonical_files = sorted((root / "data" / "lake" / "canonical" / dataset_id).rglob("*.parquet"))
    expected_paths = {
        "bars_1m": canonical_files,
        "bars_5m": [_artifact_path(root, dataset_id, "bars_5min")],
        "bars_15m": [_artifact_path(root, dataset_id, "bars_15min")],
        "dataset_manifests": [_artifact_path(root, dataset_id, "dataset_manifests")],
        "symbol_session_quality": [_artifact_path(root, dataset_id, "symbol_session_quality")],
    }

    with catalog.connect_catalog(root=root) as connection:
        definitions = dict(
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

    assert set(definitions) == set(expected_paths)
    for view_name, paths in expected_paths.items():
        assert "read_parquet" in definitions[view_name]
        assert definitions[view_name].count(".parquet") == len(paths)
        for path in paths:
            assert path.resolve().as_posix() in definitions[view_name]


def test_accept_verifies_hashes_schema_coverage_lineage_and_catalog_queries(
    tmp_path: Path,
) -> None:
    root, dataset_id = _snapshot(tmp_path)
    catalog = _catalog_module()
    catalog.build_catalog(dataset_id, root=root)

    summary = catalog.accept_dataset(dataset_id, root=root)

    assert summary.dataset_id == dataset_id
    assert summary.quality_passed is True
    assert summary.production_symbols == PRODUCTION_SYMBOLS
    assert summary.bar_counts == {"1min": 1_170, "5min": 234, "15min": 78}


def test_accept_rejects_derived_bar_drift(tmp_path: Path) -> None:
    root, dataset_id = _snapshot(tmp_path)
    catalog = _catalog_module()
    catalog.build_catalog(dataset_id, root=root)
    derived_part = next(
        (root / "data" / "lake" / "derived" / dataset_id / "bar_size=5min").glob("*.parquet")
    )
    with derived_part.open("ab") as output:
        output.write(b"drift")

    with pytest.raises(catalog.CatalogAcceptanceError, match="derived.*hash"):
        catalog.accept_dataset(dataset_id, root=root)


def test_accept_rejects_rehashed_derived_values_not_reproducible_from_parent(
    tmp_path: Path,
) -> None:
    root, dataset_id = _snapshot(tmp_path)
    catalog = _catalog_module()
    catalog.build_catalog(dataset_id, root=root)
    derived_root = root / "data" / "lake" / "derived" / dataset_id
    derived_part = next((derived_root / "bar_size=5min").glob("*.parquet"))
    bars = pd.read_parquet(derived_part)
    bars.loc[0, "close"] = 9_999.0
    bars.to_parquet(derived_part, index=False)
    lineage_path = derived_root / "lineage.json"
    lineage = json.loads(lineage_path.read_text(encoding="utf-8"))
    lineage["artifacts"]["bars_5min"]["sha256"] = hashlib.sha256(
        derived_part.read_bytes()
    ).hexdigest()
    lineage_path.write_text(json.dumps(lineage), encoding="utf-8")

    with pytest.raises(catalog.CatalogAcceptanceError, match="derived 5min content"):
        catalog.build_catalog(dataset_id, root=root)
    with pytest.raises(catalog.CatalogAcceptanceError, match="derived 5min content"):
        catalog.accept_dataset(dataset_id, root=root)


@pytest.mark.parametrize(
    ("field_name", "replacement"),
    [
        ("schema_version", "999.0.0"),
        ("source_sha256", "0" * 64),
        ("content_sha256", "f" * 64),
        ("row_count", 9_999),
    ],
)
def test_rehashed_manifest_metadata_tampering_is_refused(
    tmp_path: Path,
    field_name: str,
    replacement: object,
) -> None:
    root, dataset_id = _snapshot(tmp_path)
    catalog = _catalog_module()
    catalog.build_catalog(dataset_id, root=root)
    artifact = _artifact_path(root, dataset_id, "dataset_manifests")
    metadata = pd.read_parquet(artifact)
    metadata.loc[0, field_name] = replacement
    metadata.to_parquet(artifact, index=False)
    _rehash_artifact(root, dataset_id, "dataset_manifests")

    with pytest.raises(catalog.CatalogAcceptanceError, match="dataset_manifests metadata"):
        catalog.build_catalog(dataset_id, root=root)
    with pytest.raises(catalog.CatalogAcceptanceError, match="dataset_manifests metadata"):
        catalog.accept_dataset(dataset_id, root=root)


@pytest.mark.parametrize(
    "mutation",
    ["counter", "remove_row", "change_row"],
)
def test_rehashed_symbol_session_quality_tampering_is_refused(
    tmp_path: Path,
    mutation: str,
) -> None:
    root, dataset_id = _snapshot(tmp_path)
    catalog = _catalog_module()
    catalog.build_catalog(dataset_id, root=root)
    artifact = _artifact_path(root, dataset_id, "symbol_session_quality")
    metadata = pd.read_parquet(artifact)
    if mutation == "counter":
        metadata.loc[0, "missing_expected_bars"] = 1
    elif mutation == "remove_row":
        metadata = metadata.iloc[:-1].reset_index(drop=True)
    else:
        metadata.loc[0, "symbol"] = "AAPL"
    metadata.to_parquet(artifact, index=False)
    _rehash_artifact(root, dataset_id, "symbol_session_quality")

    with pytest.raises(catalog.CatalogAcceptanceError, match="symbol_session_quality metadata"):
        catalog.build_catalog(dataset_id, root=root)
    with pytest.raises(catalog.CatalogAcceptanceError, match="symbol_session_quality metadata"):
        catalog.accept_dataset(dataset_id, root=root)


def test_build_catalog_refuses_to_replace_drifted_derived_artifacts(
    tmp_path: Path,
) -> None:
    root, dataset_id = _snapshot(tmp_path)
    catalog = _catalog_module()
    catalog.build_catalog(dataset_id, root=root)
    derived_part = next(
        (root / "data" / "lake" / "derived" / dataset_id / "bar_size=5min").glob("*.parquet")
    )
    with derived_part.open("ab") as output:
        output.write(b"drift")

    with pytest.raises(catalog.CatalogAcceptanceError, match="derived.*hash"):
        catalog.build_catalog(dataset_id, root=root)


def test_accept_rejects_unsupported_snapshot_manifest_schema(tmp_path: Path) -> None:
    root, dataset_id = _snapshot(tmp_path)
    catalog = _catalog_module()
    catalog.build_catalog(dataset_id, root=root)
    manifest_path = root / "data" / "lake" / "canonical" / dataset_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "999.0.0"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(catalog.CatalogAcceptanceError, match="manifest schema version"):
        catalog.accept_dataset(dataset_id, root=root)


def test_accept_rejects_snapshot_without_all_production_symbols(tmp_path: Path) -> None:
    root, dataset_id = _snapshot(
        tmp_path,
        symbols=("AAPL",),
        production_symbols=(),
    )
    catalog = _catalog_module()
    catalog.build_catalog(dataset_id, root=root)

    with pytest.raises(catalog.CatalogAcceptanceError, match="IWM,QQQ,SPY"):
        catalog.accept_dataset(dataset_id, root=root)


def test_catalog_cli_builds_and_accepts_synthetic_snapshot(tmp_path: Path) -> None:
    root, dataset_id = _snapshot(tmp_path)

    built = RUNNER.invoke(
        app,
        [
            "data",
            "build-catalog",
            "--dataset-id",
            dataset_id,
            "--root",
            str(root),
        ],
    )
    accepted = RUNNER.invoke(
        app,
        [
            "data",
            "accept",
            "--dataset-id",
            dataset_id,
            "--root",
            str(root),
        ],
    )

    assert built.exit_code == 0, built.output
    assert built.stdout.strip() == str(root / "data" / "catalog" / "research.duckdb")
    assert accepted.exit_code == 0, accepted.output
    assert f"dataset_id: {dataset_id}" in accepted.stdout
    assert "quality_passed: true" in accepted.stdout
    assert "bars_1m: 1170" in accepted.stdout
    assert "bars_5m: 234" in accepted.stdout
    assert "bars_15m: 78" in accepted.stdout


def test_catalog_cli_accept_exits_nonzero_on_derived_drift(tmp_path: Path) -> None:
    root, dataset_id = _snapshot(tmp_path)
    catalog = _catalog_module()
    catalog.build_catalog(dataset_id, root=root)
    derived_part = next(
        (root / "data" / "lake" / "derived" / dataset_id / "bar_size=15min").glob("*.parquet")
    )
    with derived_part.open("ab") as output:
        output.write(b"drift")

    result = RUNNER.invoke(
        app,
        [
            "data",
            "accept",
            "--dataset-id",
            dataset_id,
            "--root",
            str(root),
        ],
    )

    assert result.exit_code != 0
