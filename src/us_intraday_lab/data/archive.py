from __future__ import annotations

import hashlib
import shutil
import tarfile
import tempfile
from collections.abc import Collection, Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import IO, cast

import pandas as pd
import pyarrow.parquet as pq  # type: ignore[import-untyped]

_APPROVED_SUFFIXES = frozenset({".csv", ".parquet"})
_READ_CHUNK_ROWS = 100_000


class UnsafeArchiveError(ValueError):
    """Raised before archive payloads are read when a member is unsafe."""


@dataclass(frozen=True, slots=True)
class ArchiveMemberInspection:
    name: str
    size: int
    columns: tuple[str, ...]
    row_estimate: int
    min_timestamp: pd.Timestamp | None
    max_timestamp: pd.Timestamp | None
    symbols: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ArchiveInspection:
    archive: Path
    source_sha256: str
    members: tuple[ArchiveMemberInspection, ...]

    @property
    def row_estimate(self) -> int:
        return sum(member.row_estimate for member in self.members)

    @property
    def columns(self) -> tuple[str, ...]:
        return tuple(sorted({column for member in self.members for column in member.columns}))

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(sorted({symbol for member in self.members for symbol in member.symbols}))

    @property
    def min_timestamp(self) -> pd.Timestamp | None:
        values = [
            member.min_timestamp for member in self.members if member.min_timestamp is not None
        ]
        return min(values) if values else None

    @property
    def max_timestamp(self) -> pd.Timestamp | None:
        values = [
            member.max_timestamp for member in self.members if member.max_timestamp is not None
        ]
        return max(values) if values else None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_member_name(name: str) -> None:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or PureWindowsPath(name).is_absolute()
        or any(part == ".." for part in path.parts)
    ):
        raise UnsafeArchiveError(f"unsafe archive member path: {name}")


def _approved_members(archive: tarfile.TarFile) -> tuple[tarfile.TarInfo, ...]:
    approved: list[tarfile.TarInfo] = []
    for member in archive.getmembers():
        _validate_member_name(member.name)
        if member.issym() or member.islnk():
            raise UnsafeArchiveError(f"archive links are not allowed: {member.name}")
        if member.isdir():
            continue
        if not member.isfile():
            raise UnsafeArchiveError(f"archive special members are not allowed: {member.name}")
        if Path(member.name).suffix.lower() in _APPROVED_SUFFIXES:
            approved.append(member)
    return tuple(approved)


def _member_stream(archive: tarfile.TarFile, member: tarfile.TarInfo) -> IO[bytes]:
    stream = archive.extractfile(member)
    if stream is None:
        raise ValueError(f"archive member cannot be read: {member.name}")
    return stream


def _csv_frames(stream: IO[bytes]) -> Iterator[pd.DataFrame]:
    yield from pd.read_csv(stream, chunksize=_READ_CHUNK_ROWS)


def _parquet_frames(stream: IO[bytes]) -> Iterator[pd.DataFrame]:
    with tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024) as spool:
        shutil.copyfileobj(stream, spool)
        spool.seek(0)
        parquet = pq.ParquetFile(spool)
        for batch in parquet.iter_batches(batch_size=_READ_CHUNK_ROWS):
            yield cast(pd.DataFrame, batch.to_pandas())


def _member_frames(
    archive: tarfile.TarFile, member: tarfile.TarInfo
) -> Iterator[pd.DataFrame]:
    with _member_stream(archive, member) as stream:
        if Path(member.name).suffix.lower() == ".csv":
            yield from _csv_frames(stream)
        else:
            yield from _parquet_frames(stream)


def _timestamp_column(columns: tuple[str, ...]) -> str | None:
    for candidate in ("date", "datetime", "timestamp"):
        if candidate in columns:
            return candidate
    return None


def _symbol_column(columns: tuple[str, ...]) -> str | None:
    for candidate in ("ticker", "symbol"):
        if candidate in columns:
            return candidate
    return None


def _inspect_member(
    archive: tarfile.TarFile, member: tarfile.TarInfo
) -> ArchiveMemberInspection:
    columns: tuple[str, ...] = ()
    row_count = 0
    min_timestamp: pd.Timestamp | None = None
    max_timestamp: pd.Timestamp | None = None
    symbols: set[str] = set()
    for frame in _member_frames(archive, member):
        frame_columns = tuple(str(column) for column in frame.columns)
        if not columns:
            columns = frame_columns
        elif frame_columns != columns:
            raise ValueError(f"schema changes within archive member: {member.name}")
        row_count += len(frame)
        timestamp_column = _timestamp_column(columns)
        if timestamp_column is not None and not frame.empty:
            timestamps = pd.to_datetime(frame[timestamp_column], utc=True, errors="coerce").dropna()
            if not timestamps.empty:
                chunk_min = pd.Timestamp(timestamps.min())
                chunk_max = pd.Timestamp(timestamps.max())
                min_timestamp = (
                    chunk_min if min_timestamp is None else min(min_timestamp, chunk_min)
                )
                max_timestamp = (
                    chunk_max if max_timestamp is None else max(max_timestamp, chunk_max)
                )
        symbol_column = _symbol_column(columns)
        if symbol_column is not None:
            symbols.update(
                frame[symbol_column].dropna().astype("string").str.strip().str.upper().tolist()
            )
    return ArchiveMemberInspection(
        name=member.name,
        size=member.size,
        columns=columns,
        row_estimate=row_count,
        min_timestamp=min_timestamp,
        max_timestamp=max_timestamp,
        symbols=tuple(sorted(symbols)),
    )


def inspect_archive(archive_path: Path) -> ArchiveInspection:
    """Inspect approved tabular members without extracting or modifying the archive."""
    resolved = archive_path.resolve(strict=True)
    source_hash = sha256_file(resolved)
    with tarfile.open(resolved, mode="r:*") as archive:
        approved = _approved_members(archive)
        members = tuple(_inspect_member(archive, member) for member in approved)
    return ArchiveInspection(
        archive=resolved,
        source_sha256=source_hash,
        members=members,
    )


def iter_archive_frames(
    archive_path: Path,
    *,
    member_names: Collection[str] | None = None,
) -> Iterator[pd.DataFrame]:
    """Yield frames only after every archive member has passed safety validation."""
    resolved = archive_path.resolve(strict=True)
    with tarfile.open(resolved, mode="r:*") as archive:
        approved = _approved_members(archive)
        requested = None if member_names is None else set(member_names)
        approved_names = {member.name for member in approved}
        if requested is not None and not requested.issubset(approved_names):
            missing = sorted(requested.difference(approved_names))
            raise ValueError(f"requested archive members are not approved: {missing}")
        for member in approved:
            if requested is None or member.name in requested:
                yield from _member_frames(archive, member)
