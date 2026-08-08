from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from us_intraday_lab.data.archive import (
    DEFAULT_ARCHIVE_READ_LIMITS,
    ArchiveReadLimits,
    inspect_archive,
    iter_archive_member_frames,
)
from us_intraday_lab.long_horizon.contracts import FiveMinuteSourceDeclaration

_SOURCE_COLUMNS = frozenset(
    {"symbol", "datetime", "open", "high", "low", "close", "volume"}
)
_OUTPUT_COLUMNS = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "provider",
    "feed",
    "session_date",
    "ingested_at",
)


def canonicalize_five_minute_rows(
    frame: pd.DataFrame,
    declaration: FiveMinuteSourceDeclaration,
) -> pd.DataFrame:
    """Convert declared naive New York bars into canonical aware UTC rows."""

    if type(frame) is not pd.DataFrame:
        raise TypeError("frame must be an exact pandas DataFrame")
    if type(declaration) is not FiveMinuteSourceDeclaration:
        raise TypeError("declaration must be an exact FiveMinuteSourceDeclaration")
    missing = sorted(_SOURCE_COLUMNS.difference(str(column) for column in frame.columns))
    if missing:
        raise ValueError("five-minute source lacks required columns: " + ",".join(missing))
    retained = frame.loc[:, sorted(_SOURCE_COLUMNS)].copy()
    symbols = retained["symbol"].astype("string")
    if set(symbols.dropna().tolist()) != set(declaration.symbols) or symbols.isna().any():
        raise ValueError("five-minute source symbols must contain exactly AAPL and QQQ")
    parsed = pd.to_datetime(retained["datetime"], errors="raise")
    if parsed.dt.tz is not None:
        raise ValueError("source timestamps must be naive America/New_York values")
    localized = parsed.dt.tz_localize(
        declaration.source_timezone,
        ambiguous="raise",
        nonexistent="raise",
    )
    retained["timestamp"] = localized.dt.tz_convert("UTC")
    retained["session_date"] = localized.dt.date
    if (
        retained["session_date"].min() < declaration.expected_start_date
        or retained["session_date"].max() > declaration.expected_end_date
    ):
        raise ValueError("source rows fall outside the declared date range")
    for column in ("open", "high", "low", "close", "volume"):
        retained[column] = pd.to_numeric(retained[column], errors="raise")
        if any(not math.isfinite(float(value)) for value in retained[column]):
            raise ValueError(f"{column} must contain finite values")
    if (retained[["open", "high", "low", "close"]] <= 0.0).any(axis=None):
        raise ValueError("OHLC prices must be positive")
    if (retained["volume"] < 0.0).any():
        raise ValueError("volume must be non-negative")
    retained["provider"] = declaration.provider
    retained["feed"] = declaration.feed
    retained["ingested_at"] = pd.Timestamp(declaration.ingested_at)
    retained = retained.drop(columns=["datetime"])
    return retained.loc[:, list(_OUTPUT_COLUMNS)].sort_values(
        ["session_date", "timestamp", "symbol"], ignore_index=True
    )


def read_declared_five_minute_member(
    archive_path: Path,
    declaration: FiveMinuteSourceDeclaration,
    *,
    limits: ArchiveReadLimits = DEFAULT_ARCHIVE_READ_LIMITS,
) -> pd.DataFrame:
    """Verify and read only the declared member, then canonicalize it."""

    if not isinstance(archive_path, Path):
        raise TypeError("archive_path must be a Path")
    if type(declaration) is not FiveMinuteSourceDeclaration:
        raise TypeError("declaration must be an exact FiveMinuteSourceDeclaration")
    inspection = inspect_archive(
        archive_path,
        member_names=(declaration.member_name,),
        limits=limits,
    )
    if len(inspection.members) != 1:
        raise ValueError("declared five-minute archive member must be unique")
    member = inspection.members[0]
    if member.name != declaration.member_name or member.sha256 != declaration.member_sha256:
        raise ValueError("declared five-minute archive member identity mismatch")
    if member.symbols != declaration.symbols:
        raise ValueError("declared five-minute archive symbol scope mismatch")
    chunks = tuple(
        frame
        for member_name, frame in iter_archive_member_frames(
            archive_path,
            member_names=(declaration.member_name,),
            limits=limits,
        )
        if member_name == declaration.member_name
    )
    if not chunks:
        raise ValueError("declared five-minute archive member contains no rows")
    canonical = canonicalize_five_minute_rows(pd.concat(chunks, ignore_index=True), declaration)
    observed_dates = canonical["session_date"]
    if (
        observed_dates.min() != declaration.expected_start_date
        or observed_dates.max() != declaration.expected_end_date
    ):
        raise ValueError("declared five-minute archive date coverage mismatch")
    return canonical
