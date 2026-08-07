from __future__ import annotations

import gzip
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

_APPROVED_SUFFIXES = frozenset({".csv", ".csv.gz", ".parquet"})
_READ_CHUNK_ROWS = 100_000


class UnsafeArchiveError(ValueError):
    """Raised before archive payloads are read when a member is unsafe."""


class ArchiveResourceLimitError(ValueError):
    """Raised when an archive exceeds a configured fail-closed resource ceiling."""


@dataclass(frozen=True, slots=True)
class ArchiveReadLimits:
    """Conservative import ceilings, sized above the planned 1.4M-row source.

    These are safety limits rather than declarations of expected archive facts.
    Callers can lower them for constrained environments or focused validation.
    """

    max_approved_members: int = 128
    max_selected_uncompressed_bytes: int = 8 * 1024**3
    max_imported_rows: int = 10_000_000
    parquet_spool_memory_bytes: int = 64 * 1024**2

    def __post_init__(self) -> None:
        for field_name in (
            "max_approved_members",
            "max_selected_uncompressed_bytes",
            "max_imported_rows",
            "parquet_spool_memory_bytes",
        ):
            if type(getattr(self, field_name)) is not int or getattr(self, field_name) <= 0:
                raise ValueError(f"{field_name} must be a positive integer")


DEFAULT_ARCHIVE_READ_LIMITS = ArchiveReadLimits()


@dataclass(frozen=True, slots=True)
class ArchiveMemberInspection:
    name: str
    size: int
    sha256: str
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


def _member_suffix(name: str) -> str:
    lowered = name.lower()
    if lowered.endswith(".csv.gz"):
        return ".csv.gz"
    return Path(lowered).suffix


def _approved_members(
    archive: tarfile.TarFile,
    *,
    limits: ArchiveReadLimits,
) -> tuple[tarfile.TarInfo, ...]:
    approved: list[tarfile.TarInfo] = []
    approved_names: set[str] = set()
    for member in archive.getmembers():
        _validate_member_name(member.name)
        if member.issym() or member.islnk():
            raise UnsafeArchiveError(f"archive links are not allowed: {member.name}")
        if member.isdir():
            continue
        if not member.isfile():
            raise UnsafeArchiveError(f"archive special members are not allowed: {member.name}")
        if _member_suffix(member.name) in _APPROVED_SUFFIXES:
            if member.name in approved_names:
                raise UnsafeArchiveError(f"duplicate approved archive member name: {member.name}")
            approved_names.add(member.name)
            approved.append(member)
            if len(approved) > limits.max_approved_members:
                raise ArchiveResourceLimitError(
                    "approved member count exceeds configured ceiling "
                    f"({limits.max_approved_members})"
                )
    return tuple(approved)


def _selected_members(
    approved: tuple[tarfile.TarInfo, ...],
    *,
    member_names: Collection[str] | None,
    limits: ArchiveReadLimits,
) -> tuple[tarfile.TarInfo, ...]:
    requested = None if member_names is None else set(member_names)
    approved_names = {member.name for member in approved}
    if requested is not None and not requested.issubset(approved_names):
        missing = sorted(requested.difference(approved_names))
        raise ValueError(f"requested archive members are not approved: {missing}")
    selected = tuple(member for member in approved if requested is None or member.name in requested)
    selected_bytes = sum(member.size for member in selected)
    if selected_bytes > limits.max_selected_uncompressed_bytes:
        raise ArchiveResourceLimitError(
            "selected uncompressed bytes exceed configured ceiling "
            f"({limits.max_selected_uncompressed_bytes})"
        )
    return selected


def _member_stream(archive: tarfile.TarFile, member: tarfile.TarInfo) -> IO[bytes]:
    stream = archive.extractfile(member)
    if stream is None:
        raise ValueError(f"archive member cannot be read: {member.name}")
    return stream


def _csv_frames(stream: IO[bytes]) -> Iterator[pd.DataFrame]:
    yield from pd.read_csv(stream, chunksize=_READ_CHUNK_ROWS)


def _parquet_frames(
    stream: IO[bytes],
    *,
    limits: ArchiveReadLimits,
) -> Iterator[pd.DataFrame]:
    with tempfile.SpooledTemporaryFile(max_size=limits.parquet_spool_memory_bytes) as spool:
        shutil.copyfileobj(stream, spool)
        spool.seek(0)
        parquet = pq.ParquetFile(spool)
        for batch in parquet.iter_batches(batch_size=_READ_CHUNK_ROWS):
            yield cast(pd.DataFrame, batch.to_pandas())


def _member_frames(
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
    *,
    limits: ArchiveReadLimits,
) -> Iterator[pd.DataFrame]:
    with _member_stream(archive, member) as stream:
        suffix = _member_suffix(member.name)
        if suffix == ".csv.gz":
            with gzip.GzipFile(fileobj=stream, mode="rb") as decompressed:
                yield from _csv_frames(cast(IO[bytes], decompressed))
        elif suffix == ".csv":
            yield from _csv_frames(stream)
        else:
            yield from _parquet_frames(stream, limits=limits)


def _member_sha256(archive: tarfile.TarFile, member: tarfile.TarInfo) -> str:
    digest = hashlib.sha256()
    with _member_stream(archive, member) as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
    *,
    limits: ArchiveReadLimits,
) -> ArchiveMemberInspection:
    columns: tuple[str, ...] = ()
    row_count = 0
    min_timestamp: pd.Timestamp | None = None
    max_timestamp: pd.Timestamp | None = None
    symbols: set[str] = set()
    member_sha256 = _member_sha256(archive, member)
    for frame in _member_frames(archive, member, limits=limits):
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
        sha256=member_sha256,
        columns=columns,
        row_estimate=row_count,
        min_timestamp=min_timestamp,
        max_timestamp=max_timestamp,
        symbols=tuple(sorted(symbols)),
    )


def inspect_archive(
    archive_path: Path,
    *,
    member_names: Collection[str] | None = None,
    limits: ArchiveReadLimits = DEFAULT_ARCHIVE_READ_LIMITS,
) -> ArchiveInspection:
    """Inspect approved tabular members without extracting or modifying the archive."""
    resolved = archive_path.resolve(strict=True)
    source_hash = sha256_file(resolved)
    with tarfile.open(resolved, mode="r:*") as archive:
        approved = _approved_members(archive, limits=limits)
        selected = _selected_members(
            approved,
            member_names=member_names,
            limits=limits,
        )
        inspected: list[ArchiveMemberInspection] = []
        imported_rows = 0
        for member in selected:
            inspection = _inspect_member(archive, member, limits=limits)
            imported_rows += inspection.row_estimate
            if imported_rows > limits.max_imported_rows:
                raise ArchiveResourceLimitError(
                    f"imported row count exceeds configured ceiling ({limits.max_imported_rows})"
                )
            inspected.append(inspection)
        members = tuple(inspected)
    return ArchiveInspection(
        archive=resolved,
        source_sha256=source_hash,
        members=members,
    )


def iter_archive_frames(
    archive_path: Path,
    *,
    member_names: Collection[str] | None = None,
    limits: ArchiveReadLimits = DEFAULT_ARCHIVE_READ_LIMITS,
) -> Iterator[pd.DataFrame]:
    """Yield selected frames after every archive member has passed safety validation."""
    for _, frame in iter_archive_member_frames(
        archive_path,
        member_names=member_names,
        limits=limits,
    ):
        yield frame


def iter_archive_member_frames(
    archive_path: Path,
    *,
    member_names: Collection[str] | None = None,
    limits: ArchiveReadLimits = DEFAULT_ARCHIVE_READ_LIMITS,
) -> Iterator[tuple[str, pd.DataFrame]]:
    """Yield selected member identities and frames after full safety validation."""
    resolved = archive_path.resolve(strict=True)
    with tarfile.open(resolved, mode="r:*") as archive:
        approved = _approved_members(archive, limits=limits)
        selected = _selected_members(
            approved,
            member_names=member_names,
            limits=limits,
        )
        imported_rows = 0
        for member in selected:
            for frame in _member_frames(archive, member, limits=limits):
                imported_rows += len(frame)
                if imported_rows > limits.max_imported_rows:
                    raise ArchiveResourceLimitError(
                        "imported row count exceeds configured ceiling "
                        f"({limits.max_imported_rows})"
                    )
                yield member.name, frame
