from __future__ import annotations

import hashlib
import io
import tarfile
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pandas as pd
from typer.testing import CliRunner

from us_intraday_lab.cli import app
from us_intraday_lab.data.calendar import expected_minute_index
from us_intraday_lab.long_horizon.catalog import (
    accept_five_minute_dataset,
    build_five_minute_catalog,
    connect_five_minute_catalog,
)
from us_intraday_lab.long_horizon.contracts import FiveMinuteSourceDeclaration
from us_intraday_lab.long_horizon.snapshot import import_five_minute_snapshot

MEMBER_NAME = "price_intraday_vol_5min.csv"
SESSIONS = (date(2026, 7, 1), date(2026, 7, 2))
RUNNER = CliRunner()


def _archive(tmp_path: Path, *, omit: tuple[str, date, int] | None = None) -> tuple[Path, str]:
    rows: list[dict[str, object]] = []
    for symbol_number, symbol in enumerate(("AAPL", "QQQ")):
        for session_date in SESSIONS:
            timestamps = expected_minute_index(session_date)[::5].tz_convert("America/New_York")
            for index, timestamp in enumerate(timestamps):
                if omit == (symbol, session_date, index):
                    continue
                price = 100.0 + symbol_number * 20 + index / 100
                rows.append(
                    {
                        "symbol": symbol,
                        "datetime": timestamp.tz_localize(None).isoformat(),
                        "open": price,
                        "high": price + 0.2,
                        "low": price - 0.2,
                        "close": price + 0.1,
                        "volume": 1_000 + index,
                    }
                )
    payload = pd.DataFrame(rows).to_csv(index=False).encode()
    archive_path = tmp_path / "five-minute.tar.gz"
    member = tarfile.TarInfo(MEMBER_NAME)
    member.size = len(payload)
    with tarfile.open(archive_path, "w:gz") as archive:
        archive.addfile(member, io.BytesIO(payload))
    return archive_path, hashlib.sha256(payload).hexdigest()


def _declaration(member_sha256: str) -> FiveMinuteSourceDeclaration:
    return FiveMinuteSourceDeclaration(
        provider="tiingo",
        feed="iex",
        bar_size="5min",
        member_name=MEMBER_NAME,
        member_sha256=member_sha256,
        symbols=("AAPL", "QQQ"),
        source_timezone="America/New_York",
        expected_start_date=SESSIONS[0],
        expected_end_date=SESSIONS[-1],
        ingested_at=datetime(2026, 7, 3, tzinfo=UTC),
    )


def test_catalog_exposes_only_shared_complete_sessions(tmp_path: Path) -> None:
    archive, member_hash = _archive(tmp_path, omit=("QQQ", SESSIONS[-1], 10))
    root = tmp_path / "repo"
    manifest = import_five_minute_snapshot(
        archive,
        _declaration(member_hash),
        root=root,
        code_revision="abc123",
    )

    catalog_path = build_five_minute_catalog(manifest.dataset_id, root=root)
    summary = accept_five_minute_dataset(manifest.dataset_id, root=root)

    assert catalog_path == (
        root / "data" / "catalog" / "long_horizon" / f"{manifest.dataset_id}.duckdb"
    )
    assert summary.accepted_sessions == 1
    assert summary.symbols == ("AAPL", "QQQ")
    assert summary.missing_expected_bars == 0
    with connect_five_minute_catalog(manifest.dataset_id, root=root) as connection:
        assert connection.execute("SELECT count(*) FROM bars_5m").fetchone() == (156,)
        assert connection.execute(
            "SELECT DISTINCT session_date FROM bars_5m ORDER BY session_date"
        ).fetchall() == [(SESSIONS[0],)]
        assert connection.execute(
            """
            SELECT missing_expected_bars, publication_state
            FROM symbol_session_quality
            WHERE symbol = 'QQQ' AND session_date = ?
            """,
            [SESSIONS[-1]],
        ).fetchone() == (1, "rejected")
        assert connection.execute(
            "SELECT count(*) FROM duckdb_tables() WHERE database_name <> 'system'"
        ).fetchone() == (0,)
        try:
            connection.execute("CREATE TABLE forbidden (value INTEGER)")
        except duckdb.Error:
            pass
        else:
            raise AssertionError("catalog must be read-only")


def test_complete_dataset_acceptance_reports_zero_missing_bars(tmp_path: Path) -> None:
    archive, member_hash = _archive(tmp_path)
    root = tmp_path / "repo"
    manifest = import_five_minute_snapshot(
        archive,
        _declaration(member_hash),
        root=root,
        code_revision="abc123",
    )
    build_five_minute_catalog(manifest.dataset_id, root=root)

    summary = accept_five_minute_dataset(manifest.dataset_id, root=root)

    assert summary.accepted_sessions == 2
    assert summary.symbols == ("AAPL", "QQQ")
    assert summary.missing_expected_bars == 0


def test_long_horizon_data_cli_imports_verifies_builds_and_accepts(tmp_path: Path) -> None:
    archive, member_hash = _archive(tmp_path)
    root = tmp_path / "repo"
    imported = RUNNER.invoke(
        app,
        [
            "long-horizon-data",
            "import",
            "--archive",
            str(archive),
            "--root",
            str(root),
            "--member-sha256",
            member_hash,
            "--expected-start-date",
            SESSIONS[0].isoformat(),
            "--expected-end-date",
            SESSIONS[-1].isoformat(),
            "--ingested-at",
            "2026-07-03T00:00:00+00:00",
            "--code-revision",
            "abc123",
        ],
    )
    assert imported.exit_code == 0, imported.output
    dataset_id = imported.output.strip()

    for command in ("verify", "build-catalog", "accept"):
        result = RUNNER.invoke(
            app,
            [
                "long-horizon-data",
                command,
                "--dataset-id",
                dataset_id,
                "--root",
                str(root),
            ],
        )
        assert result.exit_code == 0, result.output
    assert '"accepted_sessions": 2' in result.output
