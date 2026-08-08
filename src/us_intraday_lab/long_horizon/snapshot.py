from __future__ import annotations

import hashlib
import importlib.metadata
import json
import shutil
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, cast

import exchange_calendars  # type: ignore[import-untyped]
import pandas as pd
from pydantic import ValidationError

from us_intraday_lab.contracts.datasets import DatasetManifest, DatasetQuality
from us_intraday_lab.data.archive import sha256_file
from us_intraday_lab.data.calendar import expected_minute_index
from us_intraday_lab.long_horizon.contracts import FiveMinuteSourceDeclaration
from us_intraday_lab.long_horizon.data import read_declared_five_minute_member

_SCHEMA_VERSION = "1.0.0"
_EVIDENCE_SCHEMA_VERSION = "1.0.0"
_CALENDAR_NAME = "XNYS"
_SYMBOLS = ("AAPL", "QQQ")


class FiveMinuteSnapshotQualityError(ValueError):
    """Raised when no shared complete AAPL/QQQ session can be published."""


class FiveMinuteSnapshotVerificationError(ValueError):
    """Raised when an immutable five-minute snapshot cannot be reproduced."""


@dataclass(frozen=True, slots=True)
class FiveMinuteSessionQuality:
    symbol: str
    session_date: date
    expected_bars: int
    observed_bars: int
    missing_expected_bars: int
    duplicate_rows: int
    unexpected_bars: int
    invalid_ohlc_rows: int
    invalid_volume_rows: int
    non_monotonic: bool
    passed: bool
    publication_state: str


def _base(root: Path) -> Path:
    return root.resolve() / "data" / "lake" / "long_horizon"


def _canonical_root(root: Path) -> Path:
    return _base(root) / "canonical"


def _snapshot_root(root: Path, dataset_id: str) -> Path:
    candidate = _canonical_root(root) / dataset_id
    if candidate.resolve().parent != _canonical_root(root).resolve():
        raise FiveMinuteSnapshotVerificationError(
            "dataset_id must identify one long-horizon canonical snapshot"
        )
    return candidate


def _package_version(package: str) -> str:
    return importlib.metadata.version(package)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _content_files(snapshot_root: Path) -> tuple[Path, ...]:
    return tuple(
        sorted(
            (
                path
                for path in snapshot_root.rglob("*")
                if path.is_file() and path.name != "manifest.json"
            ),
            key=lambda path: path.relative_to(snapshot_root).as_posix(),
        )
    )


def _content_sha256(snapshot_root: Path) -> str:
    digest = hashlib.sha256()
    for path in _content_files(snapshot_root):
        relative = path.relative_to(snapshot_root).as_posix().encode()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _declared_sessions(declaration: FiveMinuteSourceDeclaration) -> tuple[date, ...]:
    calendar = exchange_calendars.get_calendar(_CALENDAR_NAME)
    sessions = calendar.sessions_in_range(
        pd.Timestamp(declaration.expected_start_date),
        pd.Timestamp(declaration.expected_end_date),
    )
    return tuple(timestamp.date() for timestamp in sessions)


def _session_quality(
    bars: pd.DataFrame,
    declaration: FiveMinuteSourceDeclaration,
) -> tuple[pd.DataFrame, tuple[date, ...]]:
    records: list[dict[str, object]] = []
    passing_by_session: dict[date, set[str]] = {}
    for session_date in _declared_sessions(declaration):
        expected = expected_minute_index(session_date)[::5]
        expected_set = set(expected)
        for symbol in _SYMBOLS:
            group = bars.loc[
                (bars["symbol"] == symbol) & (bars["session_date"] == session_date)
            ]
            timestamps = pd.DatetimeIndex(group["timestamp"])
            observed_set = set(timestamps)
            duplicate_rows = int(timestamps.duplicated().sum())
            missing = len(expected_set.difference(observed_set))
            unexpected = len(observed_set.difference(expected_set))
            invalid_ohlc = int(
                (
                    (group["high"] < group[["open", "close", "low"]].max(axis=1))
                    | (group["low"] > group[["open", "close", "high"]].min(axis=1))
                ).sum()
            )
            invalid_volume = int((group["volume"] < 0).sum())
            non_monotonic = not timestamps.is_monotonic_increasing
            passed = (
                len(group) == len(expected)
                and duplicate_rows == 0
                and missing == 0
                and unexpected == 0
                and invalid_ohlc == 0
                and invalid_volume == 0
                and not non_monotonic
            )
            if passed:
                passing_by_session.setdefault(session_date, set()).add(symbol)
            records.append(
                {
                    "symbol": symbol,
                    "session_date": session_date,
                    "expected_bars": len(expected),
                    "observed_bars": len(group),
                    "missing_expected_bars": missing,
                    "duplicate_rows": duplicate_rows,
                    "unexpected_bars": unexpected,
                    "invalid_ohlc_rows": invalid_ohlc,
                    "invalid_volume_rows": invalid_volume,
                    "non_monotonic": non_monotonic,
                    "passed": passed,
                }
            )
    accepted = tuple(
        session_date
        for session_date in _declared_sessions(declaration)
        if passing_by_session.get(session_date) == set(_SYMBOLS)
    )
    accepted_set = set(accepted)
    for record in records:
        record["publication_state"] = (
            "accepted" if cast(date, record["session_date"]) in accepted_set else "rejected"
        )
    quality = pd.DataFrame(records).sort_values(
        ["session_date", "symbol"], kind="stable", ignore_index=True
    )
    return quality, accepted


def _write_partitions(bars: pd.DataFrame, target: Path) -> None:
    for (raw_session_date, raw_symbol), group in bars.groupby(
        ["session_date", "symbol"], sort=True, observed=True
    ):
        session_date = cast(date, raw_session_date)
        symbol = str(raw_symbol)
        output = (
            target
            / "bar_size=5min"
            / f"session_date={session_date.isoformat()}"
            / f"symbol={symbol}"
            / "part-00000.parquet"
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        group.reset_index(drop=True).to_parquet(output, index=False)


def _declaration_record(declaration: FiveMinuteSourceDeclaration) -> dict[str, Any]:
    return declaration.model_dump(mode="json")


def _dataset_identity(
    *,
    content_sha256: str,
    source_sha256: str,
    declaration: FiveMinuteSourceDeclaration,
    calendar_version: str,
    code_revision: str,
) -> str:
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "content_sha256": content_sha256,
        "source_sha256": source_sha256,
        "member_sha256": declaration.member_sha256,
        "declaration": _declaration_record(declaration),
        "calendar_name": _CALENDAR_NAME,
        "calendar_version": calendar_version,
        "code_revision": code_revision,
    }
    return hashlib.sha256(_canonical_json(payload).encode()).hexdigest()


def import_five_minute_snapshot(
    archive_path: Path,
    declaration: FiveMinuteSourceDeclaration,
    *,
    root: Path,
    code_revision: str = "working-tree",
) -> DatasetManifest:
    """Publish shared complete five-minute sessions as an immutable snapshot."""

    bars = read_declared_five_minute_member(archive_path, declaration)
    if declaration.ingested_at < bars["timestamp"].max().to_pydatetime():
        raise ValueError("ingested_at must not precede the maximum source timestamp")
    quality, accepted_sessions = _session_quality(bars, declaration)
    if not accepted_sessions:
        raise FiveMinuteSnapshotQualityError("no shared complete AAPL/QQQ sessions")
    published = bars.loc[bars["session_date"].isin(accepted_sessions)].reset_index(drop=True)
    source_sha256 = sha256_file(archive_path)
    calendar_version = _package_version("exchange-calendars")
    canonical_root = _canonical_root(root)
    canonical_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".snapshot-", dir=canonical_root)).resolve()
    try:
        _write_partitions(published, temporary)
        metadata = temporary / "metadata"
        metadata.mkdir(parents=True)
        quality.to_parquet(metadata / "symbol_session_quality.parquet", index=False)
        evidence = {
            "schema_version": _EVIDENCE_SCHEMA_VERSION,
            "source_uri": archive_path.resolve().as_uri(),
            "source_sha256": source_sha256,
            "member_sha256": declaration.member_sha256,
            "source_declaration": _declaration_record(declaration),
            "calendar_name": _CALENDAR_NAME,
            "calendar_version": calendar_version,
            "code_revision": code_revision,
            "accepted_sessions": [value.isoformat() for value in accepted_sessions],
        }
        (temporary / "import-evidence.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        content_sha256 = _content_sha256(temporary)
        identity = _dataset_identity(
            content_sha256=content_sha256,
            source_sha256=source_sha256,
            declaration=declaration,
            calendar_version=calendar_version,
            code_revision=code_revision,
        )
        dataset_id = f"tiingo-iex-5min-{identity[:32]}"
        manifest = DatasetManifest(
            dataset_id=dataset_id,
            schema_version=_SCHEMA_VERSION,
            source_uri=archive_path.resolve().as_uri(),
            source_sha256=source_sha256,
            content_sha256=content_sha256,
            code_revision=code_revision,
            calendar_name=_CALENDAR_NAME,
            calendar_version=calendar_version,
            created_at=declaration.ingested_at,
            provider=declaration.provider,
            feed=declaration.feed,
            bar_size=declaration.bar_size,
            row_count=len(published),
            symbols=_SYMBOLS,
            min_timestamp=published["timestamp"].min().to_pydatetime(),
            max_timestamp=published["timestamp"].max().to_pydatetime(),
            quality=DatasetQuality(passed=True),
        )
        (temporary / "manifest.json").write_text(
            manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        final_root = _snapshot_root(root, dataset_id)
        if final_root.exists():
            existing = verify_five_minute_snapshot(dataset_id, root=root)
            if existing != manifest:
                raise FiveMinuteSnapshotVerificationError(
                    "dataset identity collision with a different snapshot"
                )
            return existing
        temporary.rename(final_root)
        return manifest
    finally:
        if temporary.exists() and temporary.parent == canonical_root.resolve():
            shutil.rmtree(temporary)


def _load_evidence(snapshot_root: Path) -> dict[str, Any]:
    try:
        evidence = json.loads((snapshot_root / "import-evidence.json").read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise FiveMinuteSnapshotVerificationError("import evidence is unreadable") from error
    if not isinstance(evidence, dict) or evidence.get("schema_version") != _EVIDENCE_SCHEMA_VERSION:
        raise FiveMinuteSnapshotVerificationError("import evidence schema is invalid")
    return cast(dict[str, Any], evidence)


def verify_five_minute_snapshot(dataset_id: str, *, root: Path) -> DatasetManifest:
    """Recompute identity, hashes, row scope, and shared-session publication."""

    snapshot_root = _snapshot_root(root, dataset_id)
    try:
        manifest = DatasetManifest.model_validate_json(
            (snapshot_root / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, ValidationError) as error:
        raise FiveMinuteSnapshotVerificationError("snapshot manifest is unreadable") from error
    if manifest.dataset_id != dataset_id:
        raise FiveMinuteSnapshotVerificationError("manifest dataset_id mismatch")
    if _content_sha256(snapshot_root) != manifest.content_sha256:
        raise FiveMinuteSnapshotVerificationError("snapshot content hash mismatch")
    evidence = _load_evidence(snapshot_root)
    try:
        declaration = FiveMinuteSourceDeclaration.model_validate(evidence["source_declaration"])
    except (KeyError, ValidationError) as error:
        raise FiveMinuteSnapshotVerificationError("source declaration is invalid") from error
    expected_identity = _dataset_identity(
        content_sha256=manifest.content_sha256,
        source_sha256=str(evidence.get("source_sha256")),
        declaration=declaration,
        calendar_version=str(evidence.get("calendar_version")),
        code_revision=str(evidence.get("code_revision")),
    )
    if dataset_id != f"tiingo-iex-5min-{expected_identity[:32]}":
        raise FiveMinuteSnapshotVerificationError("snapshot dataset identity mismatch")
    files = tuple(sorted(snapshot_root.glob("bar_size=5min/session_date=*/symbol=*/part-00000.parquet")))
    if not files:
        raise FiveMinuteSnapshotVerificationError("snapshot contains no five-minute partitions")
    bars = pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)
    if len(bars) != manifest.row_count or tuple(sorted(bars["symbol"].unique())) != _SYMBOLS:
        raise FiveMinuteSnapshotVerificationError("snapshot row or symbol scope mismatch")
    accepted = tuple(date.fromisoformat(value) for value in evidence["accepted_sessions"])
    if tuple(sorted(bars["session_date"].unique())) != accepted:
        raise FiveMinuteSnapshotVerificationError("snapshot accepted-session scope mismatch")
    if manifest.source_sha256 != evidence.get("source_sha256"):
        raise FiveMinuteSnapshotVerificationError("snapshot source hash mismatch")
    return manifest


def read_five_minute_snapshot(dataset_id: str, *, root: Path) -> pd.DataFrame:
    """Read a verified accepted five-minute snapshot."""

    verify_five_minute_snapshot(dataset_id, root=root)
    files = tuple(
        sorted(
            _snapshot_root(root, dataset_id).glob(
                "bar_size=5min/session_date=*/symbol=*/part-00000.parquet"
            )
        )
    )
    return pd.concat([pd.read_parquet(path) for path in files], ignore_index=True).sort_values(
        ["session_date", "timestamp", "symbol"], ignore_index=True
    )
