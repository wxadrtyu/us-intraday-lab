import hashlib
import io
import tarfile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from us_intraday_lab.cli import app
from us_intraday_lab.data.archive import UnsafeArchiveError, inspect_archive, sha256_file
from us_intraday_lab.data.snapshot import (
    SnapshotQualityError,
    SnapshotVerificationError,
    import_snapshot,
    verify_snapshot,
)

FIXTURE = Path(__file__).parents[2] / "fixtures" / "bars" / "minute_bars_valid.csv"
RUNNER = CliRunner()


def _archive_fixture(tmp_path: Path) -> Path:
    archive_path = tmp_path / "minute-bars.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(FIXTURE, arcname="legacy/minute_bars.csv")
    return archive_path


def _tar_with_member(tmp_path: Path, *, name: str, payload: bytes) -> Path:
    archive_path = tmp_path / (hashlib.sha256(name.encode()).hexdigest() + ".tar.gz")
    member = tarfile.TarInfo(name)
    member.size = len(payload)
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.addfile(member, io.BytesIO(payload))
    return archive_path


def _archive_with_unrelated_csv(tmp_path: Path) -> Path:
    archive_path = tmp_path / "mixed-members.tar.gz"
    unrelated = b"symbol,name\nAAPL,Apple\n"
    metadata = tarfile.TarInfo("metadata.csv")
    metadata.size = len(unrelated)
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(FIXTURE, arcname="legacy/minute_bars.csv")
        archive.addfile(metadata, io.BytesIO(unrelated))
    return archive_path


def test_imports_synthetic_archive_as_partitioned_immutable_snapshot(tmp_path: Path) -> None:
    archive_path = _archive_fixture(tmp_path)

    manifest, output = import_snapshot(archive_path, root=tmp_path / "repo")

    assert manifest.source_sha256 == sha256_file(archive_path)
    assert manifest.source_sha256 == hashlib.sha256(archive_path.read_bytes()).hexdigest()
    assert manifest.provider == "tiingo"
    assert manifest.feed == "iex"
    assert manifest.bar_size == "1min"
    assert manifest.row_count == 20
    assert output.exists()
    assert output.name == "part-00000.parquet"
    snapshot_root = output.parents[3]
    assert (snapshot_root / "manifest.json").exists()
    assert len(tuple(snapshot_root.rglob("part-00000.parquet"))) == 2
    assert "bar_size=1min" in output.parts
    assert "session_date=2026-07-02" in output.parts


def test_import_streams_only_members_with_the_required_minute_schema(tmp_path: Path) -> None:
    archive_path = _archive_with_unrelated_csv(tmp_path)

    manifest, _ = import_snapshot(archive_path, root=tmp_path / "repo")

    assert manifest.row_count == 20
    assert manifest.symbols == ("AAPL", "MSFT")


def test_inspection_reports_member_schema_rows_dates_symbols_and_hash(tmp_path: Path) -> None:
    archive_path = _archive_fixture(tmp_path)

    inspection = inspect_archive(archive_path)

    assert inspection.source_sha256 == sha256_file(archive_path)
    assert inspection.row_estimate == 20
    assert inspection.columns == ("close", "date", "high", "low", "open", "ticker", "volume")
    assert inspection.symbols == ("AAPL", "MSFT")
    assert inspection.min_timestamp is not None
    assert inspection.min_timestamp.isoformat() == "2026-07-02T13:30:00+00:00"
    assert inspection.max_timestamp is not None
    assert inspection.max_timestamp.isoformat() == "2026-07-02T13:39:00+00:00"
    assert inspection.members[0].name == "legacy/minute_bars.csv"
    assert inspection.members[0].size == FIXTURE.stat().st_size


def test_inspection_detects_legacy_datetime_column(tmp_path: Path) -> None:
    payload = (
        b"symbol,datetime,open,high,low,close,volume\n"
        b"AAPL,2025-06-23T13:30:00Z,1.0,1.2,0.9,1.1,100\n"
        b"AAPL,2026-07-02T19:59:00Z,1.1,1.3,1.0,1.2,200\n"
    )
    archive_path = _tar_with_member(
        tmp_path,
        name="price_intraday_1min.csv",
        payload=payload,
    )

    member = inspect_archive(archive_path).members[0]

    assert member.min_timestamp is not None
    assert member.min_timestamp.isoformat() == "2025-06-23T13:30:00+00:00"
    assert member.max_timestamp is not None
    assert member.max_timestamp.isoformat() == "2026-07-02T19:59:00+00:00"


@pytest.mark.parametrize("name", ["/absolute.csv", "../escape.csv", r"C:\escape.csv"])
def test_inspection_rejects_absolute_and_traversal_members(tmp_path: Path, name: str) -> None:
    archive_path = _tar_with_member(tmp_path, name=name, payload=FIXTURE.read_bytes())

    with pytest.raises(UnsafeArchiveError, match="unsafe archive member path"):
        inspect_archive(archive_path)


@pytest.mark.parametrize("member_type", [tarfile.SYMTYPE, tarfile.LNKTYPE])
def test_inspection_rejects_links(tmp_path: Path, member_type: bytes) -> None:
    archive_path = tmp_path / f"link-{member_type!r}.tar.gz"
    member = tarfile.TarInfo("legacy/minute_bars.csv")
    member.type = member_type
    member.linkname = "elsewhere.csv"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.addfile(member)

    with pytest.raises(UnsafeArchiveError, match="links are not allowed"):
        inspect_archive(archive_path)


def test_import_never_overwrites_an_accepted_snapshot(tmp_path: Path) -> None:
    archive_path = _archive_fixture(tmp_path)
    root = tmp_path / "repo"
    manifest, output = import_snapshot(archive_path, root=root)
    original = output.read_bytes()

    with pytest.raises(FileExistsError, match="immutable snapshot already exists"):
        import_snapshot(archive_path, root=root)

    assert output.read_bytes() == original
    canonical = root / "data" / "lake" / "canonical"
    assert [path.name for path in canonical.iterdir()] == [manifest.dataset_id]


def test_failed_production_quality_leaves_no_snapshot_or_temporary_directory(
    tmp_path: Path,
) -> None:
    payload = (
        b"ticker,date,open,high,low,close,volume\n"
        b"SPY,2026-07-02T13:30:00Z,1.0,1.2,0.9,1.1,100\n"
    )
    archive_path = _tar_with_member(tmp_path, name="minute.csv", payload=payload)
    root = tmp_path / "repo"

    with pytest.raises(SnapshotQualityError, match="SPY/2026-07-02"):
        import_snapshot(archive_path, root=root)

    canonical = root / "data" / "lake" / "canonical"
    assert not canonical.exists() or not tuple(canonical.iterdir())


def test_verify_snapshot_detects_content_tampering(tmp_path: Path) -> None:
    archive_path = _archive_fixture(tmp_path)
    root = tmp_path / "repo"
    manifest, output = import_snapshot(archive_path, root=root)

    assert verify_snapshot(manifest.dataset_id, root=root) == manifest
    with output.open("ab") as tampered:
        tampered.write(b"tampered")

    with pytest.raises(SnapshotVerificationError, match="content hash"):
        verify_snapshot(manifest.dataset_id, root=root)


def test_verify_snapshot_detects_untracked_parquet_content(tmp_path: Path) -> None:
    archive_path = _archive_fixture(tmp_path)
    root = tmp_path / "repo"
    manifest, output = import_snapshot(archive_path, root=root)
    unexpected = output.parents[3] / "unexpected.parquet"
    unexpected.write_bytes(output.read_bytes())

    with pytest.raises(SnapshotVerificationError, match="content hash"):
        verify_snapshot(manifest.dataset_id, root=root)


def test_data_cli_inspects_and_verifies_a_snapshot(tmp_path: Path) -> None:
    archive_path = _archive_fixture(tmp_path)
    root = tmp_path / "repo"
    manifest, _ = import_snapshot(archive_path, root=root)

    inspection = RUNNER.invoke(
        app,
        ["data", "inspect-archive", "--archive", str(archive_path)],
    )
    verification = RUNNER.invoke(
        app,
        [
            "data",
            "verify-snapshot",
            "--dataset-id",
            manifest.dataset_id,
            "--root",
            str(root),
        ],
    )

    assert inspection.exit_code == 0
    assert "legacy/minute_bars.csv" in inspection.stdout
    assert "ticker" in inspection.stdout
    assert verification.exit_code == 0
    assert verification.stdout.strip() == manifest.dataset_id


def test_data_cli_import_prints_dataset_id_only_after_success(tmp_path: Path) -> None:
    archive_path = _archive_fixture(tmp_path)
    root = tmp_path / "repo"

    result = RUNNER.invoke(
        app,
        [
            "data",
            "import-archive",
            "--archive",
            str(archive_path),
            "--root",
            str(root),
        ],
    )

    assert result.exit_code == 0
    assert result.stdout.strip().startswith("tiingo-iex-1min-")
