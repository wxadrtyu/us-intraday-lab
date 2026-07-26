import hashlib
import io
import json
import tarfile
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

import us_intraday_lab.data.snapshot as snapshot_module
from us_intraday_lab.cli import app
from us_intraday_lab.data.archive import UnsafeArchiveError, inspect_archive, sha256_file
from us_intraday_lab.data.calendar import expected_minute_index
from us_intraday_lab.data.snapshot import (
    ArchiveSourceDeclaration,
    SnapshotQualityError,
    SnapshotVerificationError,
    import_snapshot,
    verify_snapshot,
)

FIXTURE = Path(__file__).parents[2] / "fixtures" / "bars" / "minute_bars_valid.csv"
RUNNER = CliRunner()
SESSION_DATE = date(2026, 7, 2)
MEMBER_NAME = "legacy/minute_bars.csv"


def _source_declaration(
    *,
    member_names: tuple[str, ...] = (MEMBER_NAME,),
    production_symbols: tuple[str, ...] = (),
) -> ArchiveSourceDeclaration:
    return ArchiveSourceDeclaration(
        provider="tiingo",
        feed="iex",
        bar_size="1min",
        member_names=member_names,
        production_symbols=production_symbols,
        expected_start_date=SESSION_DATE,
        expected_end_date=SESSION_DATE,
    )


def _archive_fixture(tmp_path: Path) -> Path:
    archive_path = tmp_path / "minute-bars.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.add(FIXTURE, arcname="legacy/minute_bars.csv")
    return archive_path


def _minute_rows(
    *symbols: str,
    limit: int | None = None,
    cadence_minutes: int = 1,
) -> bytes:
    lines = ["ticker,date,open,high,low,close,volume"]
    timestamps = expected_minute_index(SESSION_DATE)[::cadence_minutes]
    if limit is not None:
        timestamps = timestamps[:limit]
    for symbol in symbols:
        for index, timestamp in enumerate(timestamps):
            price = 100.0 + index / 100
            lines.append(
                f"{symbol},{timestamp.isoformat()},{price:.2f},{price + 0.2:.2f},"
                f"{price - 0.1:.2f},{price + 0.1:.2f},{1000 + index}"
            )
    return ("\n".join(lines) + "\n").encode()


def _complete_archive_fixture(
    tmp_path: Path,
    *symbols: str,
    member_name: str = MEMBER_NAME,
) -> Path:
    return _tar_with_member(
        tmp_path,
        name=member_name,
        payload=_minute_rows(*symbols),
    )


def _tar_with_member(tmp_path: Path, *, name: str, payload: bytes) -> Path:
    archive_path = tmp_path / (hashlib.sha256(name.encode()).hexdigest() + ".tar.gz")
    member = tarfile.TarInfo(name)
    member.size = len(payload)
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.addfile(member, io.BytesIO(payload))
    return archive_path


def _archive_with_unrelated_csv(tmp_path: Path) -> Path:
    archive_path = tmp_path / "mixed-members.tar.gz"
    minute_rows = _minute_rows("AAPL", "MSFT")
    minute_member = tarfile.TarInfo(MEMBER_NAME)
    minute_member.size = len(minute_rows)
    unrelated = b"symbol,name\nAAPL,Apple\n"
    metadata = tarfile.TarInfo("metadata.csv")
    metadata.size = len(unrelated)
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.addfile(minute_member, io.BytesIO(minute_rows))
        archive.addfile(metadata, io.BytesIO(unrelated))
    return archive_path


def test_imports_synthetic_archive_as_partitioned_immutable_snapshot(tmp_path: Path) -> None:
    archive_path = _complete_archive_fixture(tmp_path, "AAPL", "MSFT")

    manifest, output = import_snapshot(
        archive_path,
        root=tmp_path / "repo",
        source=_source_declaration(),
    )

    assert manifest.source_sha256 == sha256_file(archive_path)
    assert manifest.source_sha256 == hashlib.sha256(archive_path.read_bytes()).hexdigest()
    assert manifest.provider == "tiingo"
    assert manifest.feed == "iex"
    assert manifest.bar_size == "1min"
    assert manifest.row_count == 780
    assert output.exists()
    assert output.name == "part-00000.parquet"
    snapshot_root = output.parents[3]
    assert (snapshot_root / "manifest.json").exists()
    assert (snapshot_root / "import-evidence.json").exists()
    assert len(tuple(snapshot_root.rglob("part-00000.parquet"))) == 2
    assert "bar_size=1min" in output.parts
    assert "session_date=2026-07-02" in output.parts


def test_import_streams_only_members_with_the_required_minute_schema(tmp_path: Path) -> None:
    archive_path = _archive_with_unrelated_csv(tmp_path)

    manifest, _ = import_snapshot(
        archive_path,
        root=tmp_path / "repo",
        source=_source_declaration(),
    )

    assert manifest.row_count == 780
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


@pytest.mark.parametrize(
    "symbol",
    ["A/B", r"A\B", "..", "../ESCAPE", r"..\ESCAPE", "C:ESCAPE", "/ABSOLUTE"],
)
def test_import_rejects_unsafe_symbol_partitions_without_writing(
    tmp_path: Path,
    symbol: str,
) -> None:
    archive_path = _tar_with_member(
        tmp_path,
        name=MEMBER_NAME,
        payload=_minute_rows(symbol, limit=2),
    )
    root = tmp_path / "repo"

    with pytest.raises(ValueError, match="unsafe canonical symbol"):
        import_snapshot(
            archive_path,
            root=root,
            source=_source_declaration(),
        )

    assert not tuple(tmp_path.rglob("*.parquet"))
    canonical = root / "data" / "lake" / "canonical"
    assert not canonical.exists() or not tuple(canonical.iterdir())


def test_import_quarantines_faulty_robustness_group_with_evidence(tmp_path: Path) -> None:
    lines = _minute_rows("AAPL", "MSFT").decode().splitlines()
    faulty = lines[1].split(",")
    faulty[3] = "99.00"
    lines[1] = ",".join(faulty)
    archive_path = _tar_with_member(
        tmp_path,
        name=MEMBER_NAME,
        payload=("\n".join(lines) + "\n").encode(),
    )

    manifest, output = import_snapshot(
        archive_path,
        root=tmp_path / "repo",
        source=_source_declaration(),
    )

    assert manifest.row_count == 390
    assert manifest.symbols == ("MSFT",)
    evidence = json.loads((output.parents[3] / "import-evidence.json").read_text())
    assert evidence["quarantined_groups"] == [
        {
            "duplicate_rows": 0,
            "invalid_ohlc_rows": 1,
            "invalid_volume_rows": 0,
            "missing_expected_bars": 0,
            "non_monotonic": False,
            "outside_session_rows": 0,
            "session_date": "2026-07-02",
            "symbol": "AAPL",
        }
    ]


def test_import_quarantines_incomplete_robustness_group_without_filling(
    tmp_path: Path,
) -> None:
    aapl = _minute_rows("AAPL", limit=10).decode().splitlines()
    msft = _minute_rows("MSFT").decode().splitlines()[1:]
    archive_path = _tar_with_member(
        tmp_path,
        name=MEMBER_NAME,
        payload=("\n".join(aapl + msft) + "\n").encode(),
    )

    manifest, output = import_snapshot(
        archive_path,
        root=tmp_path / "repo",
        source=_source_declaration(),
    )

    assert manifest.row_count == 390
    assert manifest.symbols == ("MSFT",)
    evidence = json.loads((output.parents[3] / "import-evidence.json").read_text())
    assert evidence["quarantined_groups"][0]["symbol"] == "AAPL"
    assert evidence["quarantined_groups"][0]["missing_expected_bars"] == 380


def test_import_attributes_source_order_fault_to_exact_robustness_group(
    tmp_path: Path,
) -> None:
    lines = _minute_rows("AAPL", "MSFT").decode().splitlines()
    lines[1], lines[2] = lines[2], lines[1]
    archive_path = _tar_with_member(
        tmp_path,
        name=MEMBER_NAME,
        payload=("\n".join(lines) + "\n").encode(),
    )

    manifest, output = import_snapshot(
        archive_path,
        root=tmp_path / "repo",
        source=_source_declaration(),
    )

    assert manifest.symbols == ("MSFT",)
    evidence = json.loads((output.parents[3] / "import-evidence.json").read_text())
    assert evidence["quarantined_groups"][0]["symbol"] == "AAPL"
    assert evidence["quarantined_groups"][0]["non_monotonic"] is True


def test_import_fails_wholly_absent_declared_production_groups(tmp_path: Path) -> None:
    archive_path = _complete_archive_fixture(tmp_path, "AAPL")
    root = tmp_path / "repo"

    with pytest.raises(SnapshotQualityError, match="SPY/2026-07-02"):
        import_snapshot(
            archive_path,
            root=root,
            source=_source_declaration(production_symbols=("SPY",)),
        )

    canonical = root / "data" / "lake" / "canonical"
    assert not canonical.exists() or not tuple(canonical.iterdir())


def test_import_always_treats_observed_core_etfs_as_production(tmp_path: Path) -> None:
    spy = _minute_rows("SPY", limit=10).decode().splitlines()
    msft = _minute_rows("MSFT").decode().splitlines()[1:]
    archive_path = _tar_with_member(
        tmp_path,
        name=MEMBER_NAME,
        payload=("\n".join(spy + msft) + "\n").encode(),
    )

    with pytest.raises(SnapshotQualityError, match="SPY/2026-07-02"):
        import_snapshot(
            archive_path,
            root=tmp_path / "repo",
            source=_source_declaration(),
        )


def test_import_rejects_declared_member_with_wrong_cadence(tmp_path: Path) -> None:
    archive_path = _tar_with_member(
        tmp_path,
        name=MEMBER_NAME,
        payload=_minute_rows("AAPL", cadence_minutes=5),
    )

    with pytest.raises(ValueError, match="one-minute cadence"):
        import_snapshot(
            archive_path,
            root=tmp_path / "repo",
            source=_source_declaration(),
        )


def test_import_rejects_undeclared_member_identity(tmp_path: Path) -> None:
    archive_path = _complete_archive_fixture(tmp_path, "AAPL")

    with pytest.raises(ValueError, match="absent or unapproved"):
        import_snapshot(
            archive_path,
            root=tmp_path / "repo",
            source=_source_declaration(member_names=("not-present.csv",)),
        )


def test_import_records_explicit_source_and_cadence_evidence(tmp_path: Path) -> None:
    archive_path = _complete_archive_fixture(tmp_path, "AAPL")

    _, output = import_snapshot(
        archive_path,
        root=tmp_path / "repo",
        source=_source_declaration(),
    )

    evidence = json.loads((output.parents[3] / "import-evidence.json").read_text())
    assert evidence["source_declaration"] == {
        "bar_size": "1min",
        "expected_end_date": "2026-07-02",
        "expected_start_date": "2026-07-02",
        "feed": "iex",
        "member_names": [MEMBER_NAME],
        "production_symbols": [],
        "provider": "tiingo",
    }
    assert evidence["observed_cadence"] == {
        "bar_size": "1min",
        "validated": True,
    }


def test_import_detects_source_drift_before_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    archive_path = _complete_archive_fixture(tmp_path, "AAPL")
    root = tmp_path / "repo"
    original_iter = snapshot_module.iter_archive_frames

    def drifting_frames(
        path: Path,
        *,
        member_names: tuple[str, ...],
    ) -> object:
        yield from original_iter(path, member_names=member_names)
        with path.open("ab") as archive:
            archive.write(b"source-drift")

    monkeypatch.setattr(snapshot_module, "iter_archive_frames", drifting_frames)

    with pytest.raises(SnapshotVerificationError, match="source archive changed"):
        import_snapshot(
            archive_path,
            root=root,
            source=_source_declaration(),
        )

    canonical = root / "data" / "lake" / "canonical"
    assert not canonical.exists() or not tuple(canonical.iterdir())


def test_import_never_overwrites_an_accepted_snapshot(tmp_path: Path) -> None:
    archive_path = _complete_archive_fixture(tmp_path, "AAPL", "MSFT")
    root = tmp_path / "repo"
    manifest, output = import_snapshot(
        archive_path,
        root=root,
        source=_source_declaration(),
    )
    original = output.read_bytes()

    with pytest.raises(FileExistsError, match="immutable snapshot already exists"):
        import_snapshot(archive_path, root=root, source=_source_declaration())

    assert output.read_bytes() == original
    canonical = root / "data" / "lake" / "canonical"
    assert [path.name for path in canonical.iterdir()] == [manifest.dataset_id]


def test_failed_production_quality_leaves_no_snapshot_or_temporary_directory(
    tmp_path: Path,
) -> None:
    payload = (
        b"ticker,date,open,high,low,close,volume\n"
        b"SPY,2026-07-02T13:30:00Z,1.0,1.2,0.9,1.1,100\n"
        b"SPY,2026-07-02T13:31:00Z,1.1,1.3,1.0,1.2,101\n"
    )
    archive_path = _tar_with_member(tmp_path, name="minute.csv", payload=payload)
    root = tmp_path / "repo"

    with pytest.raises(SnapshotQualityError, match="SPY/2026-07-02"):
        import_snapshot(
            archive_path,
            root=root,
            source=_source_declaration(
                member_names=("minute.csv",),
                production_symbols=("SPY",),
            ),
        )

    canonical = root / "data" / "lake" / "canonical"
    assert not canonical.exists() or not tuple(canonical.iterdir())


def test_verify_snapshot_detects_content_tampering(tmp_path: Path) -> None:
    archive_path = _complete_archive_fixture(tmp_path, "AAPL", "MSFT")
    root = tmp_path / "repo"
    manifest, output = import_snapshot(
        archive_path,
        root=root,
        source=_source_declaration(),
    )

    assert verify_snapshot(manifest.dataset_id, root=root) == manifest
    with output.open("ab") as tampered:
        tampered.write(b"tampered")

    with pytest.raises(SnapshotVerificationError, match="content hash"):
        verify_snapshot(manifest.dataset_id, root=root)


def test_verify_snapshot_detects_untracked_parquet_content(tmp_path: Path) -> None:
    archive_path = _complete_archive_fixture(tmp_path, "AAPL", "MSFT")
    root = tmp_path / "repo"
    manifest, output = import_snapshot(
        archive_path,
        root=root,
        source=_source_declaration(),
    )
    unexpected = output.parents[3] / "unexpected.parquet"
    unexpected.write_bytes(output.read_bytes())

    with pytest.raises(SnapshotVerificationError, match="content hash"):
        verify_snapshot(manifest.dataset_id, root=root)


def test_data_cli_inspects_and_verifies_a_snapshot(tmp_path: Path) -> None:
    archive_path = _complete_archive_fixture(tmp_path, "AAPL", "MSFT")
    root = tmp_path / "repo"
    manifest, _ = import_snapshot(
        archive_path,
        root=root,
        source=_source_declaration(),
    )

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
    archive_path = _complete_archive_fixture(tmp_path, "SPY")
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
            "--provider",
            "tiingo",
            "--feed",
            "iex",
            "--bar-size",
            "1min",
            "--member",
            MEMBER_NAME,
            "--production-symbol",
            "SPY",
            "--expected-start-date",
            "2026-07-02",
            "--expected-end-date",
            "2026-07-02",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout.strip().startswith("tiingo-iex-1min-")
