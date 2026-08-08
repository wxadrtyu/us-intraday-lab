from __future__ import annotations

import hashlib
import io
import tarfile
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from us_intraday_lab.data.calendar import expected_minute_index
from us_intraday_lab.long_horizon.contracts import FiveMinuteSourceDeclaration
from us_intraday_lab.long_horizon.snapshot import (
    FiveMinuteSnapshotVerificationError,
    import_five_minute_snapshot,
    verify_five_minute_snapshot,
)

MEMBER_NAME = "price_intraday_vol_5min.csv"
SESSIONS = (date(2026, 7, 1), date(2026, 7, 2))


def _payload(*, omit: tuple[str, date, int] | None = None) -> bytes:
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
    return pd.DataFrame(rows).to_csv(index=False).encode()


def _archive(tmp_path: Path, *, omit: tuple[str, date, int] | None = None) -> tuple[Path, str]:
    payload = _payload(omit=omit)
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


def test_snapshot_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    archive, member_hash = _archive(tmp_path)

    first = import_five_minute_snapshot(
        archive,
        _declaration(member_hash),
        root=tmp_path / "repo",
        code_revision="abc123",
    )
    second = import_five_minute_snapshot(
        archive,
        _declaration(member_hash),
        root=tmp_path / "repo",
        code_revision="abc123",
    )

    assert first == second
    assert first.dataset_id.startswith("tiingo-iex-5min-")
    assert first.bar_size == "5min"
    assert first.symbols == ("AAPL", "QQQ")
    snapshot_root = (
        tmp_path / "repo" / "data" / "lake" / "long_horizon" / "canonical" / first.dataset_id
    )
    assert len(tuple(snapshot_root.rglob("part-00000.parquet"))) == 4
    assert verify_five_minute_snapshot(first.dataset_id, root=tmp_path / "repo") == first


def test_snapshot_verification_detects_partition_tampering(tmp_path: Path) -> None:
    archive, member_hash = _archive(tmp_path)
    manifest = import_five_minute_snapshot(
        archive,
        _declaration(member_hash),
        root=tmp_path / "repo",
        code_revision="abc123",
    )
    snapshot_root = (
        tmp_path
        / "repo"
        / "data"
        / "lake"
        / "long_horizon"
        / "canonical"
        / manifest.dataset_id
    )
    partition = next(snapshot_root.rglob("part-00000.parquet"))
    partition.write_bytes(partition.read_bytes() + b"tampered")

    with pytest.raises(FiveMinuteSnapshotVerificationError, match="content hash"):
        verify_five_minute_snapshot(manifest.dataset_id, root=tmp_path / "repo")

