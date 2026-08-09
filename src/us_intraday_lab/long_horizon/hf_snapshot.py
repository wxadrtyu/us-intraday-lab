from __future__ import annotations

import hashlib
import importlib.metadata
import json
import shutil
import tempfile
from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
from pydantic import ValidationError

from us_intraday_lab.contracts.datasets import DatasetManifest, DatasetQuality

_SCHEMA_VERSION = "1.0.0"
_DEFAULT_SYMBOLS = ("SPY", "IWM")
_DEFAULT_SLUG = "spy-iwm"
_REPOSITORY = "mito0o852/OHLCV-1m"


class HfFiveMinuteSnapshotError(ValueError):
    """Raised when the independently sourced HF snapshot is not reproducible."""


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _snapshot_root(root: Path, dataset_id: str) -> Path:
    canonical = root.resolve() / "data" / "lake" / "long_horizon" / "canonical"
    candidate = canonical / dataset_id
    if candidate.resolve().parent != canonical.resolve():
        raise HfFiveMinuteSnapshotError("dataset_id must identify one canonical snapshot")
    return candidate


def _month_values(start: str, end: str) -> tuple[str, ...]:
    first = date.fromisoformat(start + "-01")
    last = date.fromisoformat(end + "-01")
    if first > last:
        raise ValueError("start month must not exceed end month")
    values: list[str] = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        values.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return tuple(values)


def _load_month_records(
    root: Path,
    *,
    start_month: str,
    end_month: str,
    slug: str,
    symbols: tuple[str, str],
) -> tuple[dict[str, Any], ...]:
    source_name = f"hf_{slug.replace('-', '_')}_5min"
    manifest_root = root / "data" / "catalog" / source_name / "months"
    records: list[dict[str, Any]] = []
    for month in _month_values(start_month, end_month):
        path = manifest_root / f"{slug}-{month}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise HfFiveMinuteSnapshotError(f"month manifest is unreadable: {month}") from error
        if (
            not isinstance(record, dict)
            or record.get("month") != month
            or tuple(record.get("symbols", ())) != symbols
            or record.get("bar_size") != "5min"
            or record.get("repository") != _REPOSITORY
        ):
            raise HfFiveMinuteSnapshotError(f"month manifest scope is invalid: {month}")
        records.append(cast(dict[str, Any], record))
    return tuple(records)


def _identity_payload(
    *,
    source_sha256: str,
    content_sha256: str,
    code_revision: str,
    symbols: tuple[str, str],
) -> dict[str, str | list[str]]:
    return {
        "schema_version": _SCHEMA_VERSION,
        "source_sha256": source_sha256,
        "content_sha256": content_sha256,
        "code_revision": code_revision,
        "repository": _REPOSITORY,
        "symbols": list(symbols),
        "bar_size": "5min",
    }


def _dataset_id(payload: Mapping[str, object]) -> str:
    identity = _sha256_bytes(_canonical_json(payload).encode())
    return f"hf-finnhub-5min-{identity[:32]}"


def publish_hf_five_minute_snapshot(
    *,
    root: Path,
    start_month: str,
    end_month: str,
    code_revision: str = "working-tree",
    created_at: datetime | None = None,
    slug: str = _DEFAULT_SLUG,
    symbols: tuple[str, str] = _DEFAULT_SYMBOLS,
) -> DatasetManifest:
    """Publish audited monthly extracts into immutable, session-isolated files."""

    root = root.resolve()
    if (
        type(slug) is not str
        or not slug
        or type(symbols) is not tuple
        or len(symbols) != 2
        or len(set(symbols)) != 2
        or any(type(symbol) is not str or not symbol for symbol in symbols)
    ):
        raise ValueError("snapshot requires a slug and an exact pair of symbols")
    records = _load_month_records(
        root,
        start_month=start_month,
        end_month=end_month,
        slug=slug,
        symbols=symbols,
    )
    canonical = root / "data" / "lake" / "long_horizon" / "canonical"
    canonical.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".hf-snapshot-", dir=canonical)).resolve()
    session_records: list[dict[str, object]] = []
    all_timestamps: list[pd.Timestamp] = []
    try:
        observed_sessions: set[date] = set()
        for record in records:
            month = str(record["month"])
            source_name = f"hf_{slug.replace('-', '_')}_5min"
            compact = root / "data" / "raw" / source_name / f"{slug}-{month}.parquet"
            if _sha256_file(compact) != record.get("output_sha256"):
                raise HfFiveMinuteSnapshotError(f"compact month hash mismatch: {month}")
            bars = pd.read_parquet(compact)
            bars["timestamp"] = pd.to_datetime(bars["timestamp"], utc=True, errors="raise")
            bars["available_at"] = pd.to_datetime(
                bars["available_at"], utc=True, errors="raise"
            )
            bars["session_date"] = pd.to_datetime(bars["session_date"]).dt.date
            declared = tuple(date.fromisoformat(value) for value in record["accepted_sessions"])
            if tuple(sorted(bars["session_date"].unique())) != declared:
                raise HfFiveMinuteSnapshotError(f"accepted-session mismatch: {month}")
            for session in declared:
                if session in observed_sessions:
                    raise HfFiveMinuteSnapshotError(f"duplicate session across months: {session}")
                group = bars.loc[bars["session_date"] == session].sort_values(
                    ["timestamp", "symbol"], kind="stable", ignore_index=True
                )
                expected_rows = 78 * len(symbols)
                if len(group) != expected_rows or set(group["symbol"].astype(str)) != set(symbols):
                    raise HfFiveMinuteSnapshotError(f"invalid session scope: {session}")
                relative = Path("sessions") / f"{session.isoformat()}.parquet"
                output = temporary / relative
                output.parent.mkdir(parents=True, exist_ok=True)
                group.to_parquet(output, index=False, compression="zstd")
                session_records.append(
                    {
                        "session_date": session.isoformat(),
                        "path": relative.as_posix(),
                        "row_count": len(group),
                        "sha256": _sha256_file(output),
                    }
                )
                observed_sessions.add(session)
                all_timestamps.extend((group["timestamp"].min(), group["timestamp"].max()))
        if not session_records:
            raise HfFiveMinuteSnapshotError("snapshot contains no accepted sessions")
        source_records = [
            {
                key: record[key]
                for key in (
                    "month",
                    "source_filename",
                    "source_sha256",
                    "output_sha256",
                    "accepted_sessions",
                    "rejected_sessions",
                    "repository",
                    "revision",
                )
            }
            for record in records
        ]
        source_sha256 = _sha256_bytes(_canonical_json(source_records).encode())
        content_sha256 = _sha256_bytes(_canonical_json(session_records).encode())
        identity_payload = _identity_payload(
            source_sha256=source_sha256,
            content_sha256=content_sha256,
            code_revision=code_revision,
            symbols=symbols,
        )
        dataset_id = _dataset_id(identity_payload)
        evidence = {
            "schema_version": _SCHEMA_VERSION,
            "identity_payload": identity_payload,
            "months": source_records,
            "sessions": session_records,
        }
        (temporary / "hf-import-evidence.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        created = created_at or datetime.now(UTC)
        manifest = DatasetManifest(
            dataset_id=dataset_id,
            schema_version=_SCHEMA_VERSION,
            source_uri=f"https://huggingface.co/datasets/{_REPOSITORY}",
            source_sha256=source_sha256,
            content_sha256=content_sha256,
            code_revision=code_revision,
            calendar_name="XNYS",
            calendar_version=importlib.metadata.version("exchange-calendars"),
            created_at=created,
            provider="huggingface",
            feed="finnhub-derived",
            bar_size="5min",
            row_count=sum(cast(int, record["row_count"]) for record in session_records),
            symbols=symbols,
            min_timestamp=min(all_timestamps).to_pydatetime(),
            max_timestamp=max(all_timestamps).to_pydatetime(),
            quality=DatasetQuality(passed=True),
        )
        (temporary / "manifest.json").write_text(
            manifest.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        final = _snapshot_root(root, dataset_id)
        if final.exists():
            existing = HfFiveMinuteSnapshotStore(root=root, dataset_id=dataset_id).manifest
            if existing != manifest:
                raise HfFiveMinuteSnapshotError("dataset identity collision")
            return existing
        temporary.rename(final)
        return manifest
    finally:
        if temporary.exists() and temporary.parent == canonical:
            shutil.rmtree(temporary)


class HfFiveMinuteSnapshotStore:
    """Expose metadata eagerly and deserialize only explicitly requested sessions."""

    def __init__(self, *, root: Path, dataset_id: str) -> None:
        self.root = _snapshot_root(root, dataset_id)
        try:
            self.manifest = DatasetManifest.model_validate_json(
                (self.root / "manifest.json").read_text(encoding="utf-8")
            )
            evidence = json.loads(
                (self.root / "hf-import-evidence.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise HfFiveMinuteSnapshotError("snapshot metadata is unreadable") from error
        if self.manifest.dataset_id != dataset_id or _dataset_id(evidence["identity_payload"]) != dataset_id:
            raise HfFiveMinuteSnapshotError("snapshot identity mismatch")
        if (
            evidence["identity_payload"].get("source_sha256") != self.manifest.source_sha256
            or evidence["identity_payload"].get("content_sha256") != self.manifest.content_sha256
            or tuple(evidence["identity_payload"].get("symbols", ()))
            != self.manifest.symbols
        ):
            raise HfFiveMinuteSnapshotError("snapshot manifest and evidence disagree")
        self.symbols = cast(tuple[str, str], self.manifest.symbols)
        if len(self.symbols) != 2 or len(set(self.symbols)) != 2:
            raise HfFiveMinuteSnapshotError("snapshot must contain an exact symbol pair")
        self._sessions = {
            date.fromisoformat(item["session_date"]): cast(dict[str, Any], item)
            for item in evidence["sessions"]
        }
        if len(self._sessions) != len(evidence["sessions"]):
            raise HfFiveMinuteSnapshotError("snapshot contains duplicate session metadata")

    @property
    def accepted_sessions(self) -> tuple[date, ...]:
        return tuple(sorted(self._sessions))

    def read_sessions(self, sessions: tuple[date, ...]) -> pd.DataFrame:
        if type(sessions) is not tuple or not sessions:
            raise TypeError("sessions must be a non-empty exact tuple")
        if tuple(sorted(sessions)) != sessions or len(set(sessions)) != len(sessions):
            raise ValueError("sessions must be sorted and unique")
        frames: list[pd.DataFrame] = []
        for session in sessions:
            try:
                record = self._sessions[session]
            except KeyError as error:
                raise HfFiveMinuteSnapshotError(f"session is outside snapshot: {session}") from error
            path = self.root / str(record["path"])
            if path.resolve().parent != (self.root / "sessions").resolve():
                raise HfFiveMinuteSnapshotError("session path escaped snapshot")
            if _sha256_file(path) != record["sha256"]:
                raise HfFiveMinuteSnapshotError(f"session hash mismatch: {session}")
            frame = pd.read_parquet(path)
            if len(frame) != record["row_count"] or set(frame["session_date"]) != {session}:
                raise HfFiveMinuteSnapshotError(f"session content mismatch: {session}")
            frames.append(frame)
        return pd.concat(frames, ignore_index=True).sort_values(
            ["session_date", "timestamp", "symbol"], kind="stable", ignore_index=True
        )
