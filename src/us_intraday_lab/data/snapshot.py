from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from importlib.metadata import PackageNotFoundError, version
from itertools import pairwise
from pathlib import Path
from typing import Literal, cast

import exchange_calendars  # type: ignore[import-untyped]
import pandas as pd
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from us_intraday_lab.contracts.datasets import DatasetManifest
from us_intraday_lab.data.archive import (
    DEFAULT_ARCHIVE_READ_LIMITS,
    ArchiveInspection,
    ArchiveReadLimits,
    inspect_archive,
    iter_archive_member_frames,
    sha256_file,
)
from us_intraday_lab.data.canonicalize import canonicalize_tiingo_rows
from us_intraday_lab.data.quality import (
    PRODUCTION_SYMBOLS,
    ExpectedGroup,
    MinuteBarsQualityAssessment,
    SymbolSessionQuality,
    assess_minute_bars,
)
from us_intraday_lab.settings import LabPaths

_BAR_SIZE = "1min"
_SCHEMA_VERSION = "1.0.0"
_EVIDENCE_SCHEMA_VERSION = "1.0.0"
_TIINGO_MINUTE_COLUMNS = frozenset({"ticker", "date", "open", "high", "low", "close", "volume"})
_CANONICAL_SYMBOL = re.compile(r"^[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)*$")
_XNYS = exchange_calendars.get_calendar("XNYS")
_NEW_YORK = "America/New_York"

DerivedBarSize = Literal["5min", "15min"]


@dataclass(frozen=True, slots=True)
class DerivedSnapshotLineage:
    """Immutable provenance attached to every derived intraday bar."""

    parent_snapshot_id: str
    bar_size: DerivedBarSize
    source_bar_size: Literal["1min"] = "1min"

    def __post_init__(self) -> None:
        if not self.parent_snapshot_id.strip():
            raise ValueError("parent_snapshot_id must not be blank")

    def metadata(self) -> dict[str, str]:
        return {
            "parent_snapshot_id": self.parent_snapshot_id,
            "source_bar_size": self.source_bar_size,
            "bar_size": self.bar_size,
        }


def _validate_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if (
        normalized != symbol
        or len(normalized) > 16
        or _CANONICAL_SYMBOL.fullmatch(normalized) is None
    ):
        raise ValueError(f"unsafe canonical symbol: {symbol!r}")
    return normalized


@dataclass(frozen=True, slots=True)
class ArchiveSourceDeclaration:
    """Explicit identity and expected production scope for one legacy import."""

    provider: str
    feed: str
    bar_size: str
    member_names: tuple[str, ...]
    production_symbols: tuple[str, ...]
    expected_start_date: date
    expected_end_date: date
    expected_robustness_groups: tuple[ExpectedGroup, ...] = ()

    def __post_init__(self) -> None:
        if (self.provider, self.feed, self.bar_size) != ("tiingo", "iex", "1min"):
            raise ValueError("only declared tiingo/iex/1min sources are supported")
        if not self.member_names or len(set(self.member_names)) != len(self.member_names):
            raise ValueError("member_names must contain unique approved member identities")
        if self.expected_start_date > self.expected_end_date:
            raise ValueError("expected_start_date must not exceed expected_end_date")
        normalized_production = tuple(
            sorted({_validate_symbol(symbol) for symbol in self.production_symbols})
        )
        if normalized_production != tuple(sorted(self.production_symbols)):
            raise ValueError("production_symbols must be unique canonical tickers")
        normalized_robustness = tuple(
            sorted(
                {
                    (_validate_symbol(symbol), session_date)
                    for symbol, session_date in self.expected_robustness_groups
                }
            )
        )
        if len(normalized_robustness) != len(self.expected_robustness_groups):
            raise ValueError("expected_robustness_groups must be unique")
        production = set(normalized_production).union(PRODUCTION_SYMBOLS)
        for symbol, session_date in normalized_robustness:
            if symbol in production:
                raise ValueError("expected robustness groups must not contain production symbols")
            if type(session_date) is not date:
                raise TypeError("expected robustness group session_date must be a date")
            if not self.expected_start_date <= session_date <= self.expected_end_date:
                raise ValueError(
                    "expected robustness groups must fall within the declared date range"
                )


class SnapshotQualityError(ValueError):
    """Raised when an import fails the production quality gate."""


class SnapshotVerificationError(ValueError):
    """Raised when an immutable snapshot no longer matches its manifest."""


def _package_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "unknown"


def _code_revision(root: Path) -> str:
    if not root.is_dir():
        return "unknown"
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    revision = result.stdout.strip()
    return revision if result.returncode == 0 and revision else "unknown"


def _content_sha256(root: Path, files: tuple[Path, ...]) -> str:
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


def _contained_path(root: Path, *parts: str) -> Path:
    resolved_root = root.resolve()
    candidate = resolved_root.joinpath(*parts).resolve()
    if not candidate.is_relative_to(resolved_root):
        raise ValueError(f"partition path escapes verified temporary root: {candidate}")
    return candidate


def _write_partitions(bars: pd.DataFrame, snapshot_root: Path) -> tuple[Path, ...]:
    outputs: list[Path] = []
    grouped = bars.groupby(["session_date", "symbol"], sort=True, observed=True)
    for (session_date, symbol), group in grouped:
        canonical_symbol = _validate_symbol(str(symbol))
        partition = _contained_path(
            snapshot_root,
            f"bar_size={_BAR_SIZE}",
            f"session_date={session_date}",
            f"symbol={canonical_symbol}",
        )
        partition.mkdir(parents=True)
        output = _contained_path(
            snapshot_root, *partition.relative_to(snapshot_root).parts, "part-00000.parquet"
        )
        group.reset_index(drop=True).to_parquet(output, index=False)
        outputs.append(output)
    return tuple(outputs)


def _safe_remove_temporary(path: Path, parent: Path) -> None:
    resolved_parent = parent.resolve()
    resolved_path = path.resolve()
    if resolved_path.parent != resolved_parent or not resolved_path.name.startswith(".snapshot-"):
        raise RuntimeError(f"refusing to remove unverified temporary directory: {path}")
    shutil.rmtree(resolved_path)


def _effective_production_symbols(
    bars: pd.DataFrame,
    source: ArchiveSourceDeclaration,
) -> tuple[str, ...]:
    observed_core = set(bars["symbol"].astype(str).tolist()).intersection(PRODUCTION_SYMBOLS)
    return tuple(sorted(set(source.production_symbols).union(observed_core)))


def _expected_production_groups(
    source: ArchiveSourceDeclaration,
    production_symbols: tuple[str, ...],
) -> set[ExpectedGroup]:
    sessions = _XNYS.sessions_in_range(
        pd.Timestamp(source.expected_start_date),
        pd.Timestamp(source.expected_end_date),
    )
    return {(symbol, session.date()) for symbol in production_symbols for session in sessions}


def _expected_source_groups(
    source: ArchiveSourceDeclaration,
    production_symbols: tuple[str, ...],
) -> set[ExpectedGroup]:
    return _expected_production_groups(source, production_symbols).union(
        source.expected_robustness_groups
    )


def _source_order_and_cadence(
    source_rows: pd.DataFrame,
) -> tuple[set[ExpectedGroup], dict[str, object]]:
    timestamps = pd.DatetimeIndex(pd.to_datetime(source_rows["date"], utc=True, errors="raise"))
    if any(
        value != 0
        for values in (timestamps.second, timestamps.microsecond, timestamps.nanosecond)
        for value in values
    ):
        raise ValueError("declared source does not have one-minute cadence alignment")
    frame = pd.DataFrame(
        {
            "symbol": source_rows["ticker"].astype("string").str.strip().str.upper(),
            "timestamp": timestamps,
            "session_date": timestamps.tz_convert(_NEW_YORK).date,
        }
    )
    non_monotonic: set[ExpectedGroup] = set()
    positive_delta_nanoseconds: list[int] = []
    for (symbol, session_date), group in frame.groupby(
        ["symbol", "session_date"],
        sort=True,
        observed=True,
    ):
        group_timestamps = group["timestamp"]
        if not group_timestamps.is_monotonic_increasing:
            non_monotonic.add((str(symbol), cast(date, session_date)))
        ordered_nanoseconds = sorted(
            {pd.Timestamp(value).value for value in group_timestamps.tolist()}
        )
        positive_delta_nanoseconds.extend(
            current - previous
            for previous, current in pairwise(ordered_nanoseconds)
            if current > previous
        )
    if (
        not positive_delta_nanoseconds
        or min(positive_delta_nanoseconds) != pd.Timedelta(minutes=1).value
    ):
        raise ValueError("declared source does not demonstrate observed one-minute cadence")
    return non_monotonic, {
        "validated": True,
        "bar_size": _BAR_SIZE,
    }


def _validate_canonical_symbols(bars: pd.DataFrame) -> None:
    for symbol in sorted(set(bars["symbol"].astype(str).tolist())):
        _validate_symbol(symbol)


def _validate_declared_date_range(
    bars: pd.DataFrame,
    source: ArchiveSourceDeclaration,
) -> None:
    observed_dates = set(bars["session_date"].tolist())
    outside = sorted(
        session_date
        for session_date in observed_dates
        if not source.expected_start_date <= session_date <= source.expected_end_date
    )
    if outside:
        raise ValueError(f"bars fall outside declared expected date range: {outside}")


def _quarantine_record(group: SymbolSessionQuality) -> dict[str, object]:
    return {
        "symbol": group.symbol,
        "session_date": group.session_date.isoformat(),
        "missing_expected_bars": group.missing_expected_bars,
        "duplicate_rows": group.duplicate_rows,
        "invalid_ohlc_rows": group.invalid_ohlc_rows,
        "invalid_volume_rows": group.invalid_volume_rows,
        "outside_session_rows": group.outside_session_rows,
        "non_monotonic": group.non_monotonic,
    }


def _source_group_quality_record(
    group: SymbolSessionQuality,
    *,
    publication_state: Literal["published", "quarantined"],
) -> dict[str, object]:
    return {
        "symbol": group.symbol,
        "session_date": group.session_date.isoformat(),
        "production": group.production,
        "expected_bars": group.expected_bars,
        "observed_bars": group.observed_bars,
        "missing_expected_bars": group.missing_expected_bars,
        "duplicate_rows": group.duplicate_rows,
        "invalid_ohlc_rows": group.invalid_ohlc_rows,
        "invalid_volume_rows": group.invalid_volume_rows,
        "outside_session_rows": group.outside_session_rows,
        "non_monotonic": group.non_monotonic,
        "structural_passed": group.structural_passed,
        "passed": group.passed,
        "requires_quarantine": group.requires_quarantine,
        "publication_state": publication_state,
    }


def _source_declaration_record(source: ArchiveSourceDeclaration) -> dict[str, object]:
    return {
        "provider": source.provider,
        "feed": source.feed,
        "bar_size": source.bar_size,
        "member_names": sorted(source.member_names),
        "production_symbols": sorted(source.production_symbols),
        "expected_start_date": source.expected_start_date.isoformat(),
        "expected_end_date": source.expected_end_date.isoformat(),
        "expected_robustness_groups": [
            {"symbol": symbol, "session_date": session_date.isoformat()}
            for symbol, session_date in sorted(source.expected_robustness_groups)
        ],
    }


def _source_recipe_sha256(source: ArchiveSourceDeclaration) -> str:
    canonical_recipe = json.dumps(
        _source_declaration_record(source),
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_recipe.encode("utf-8")).hexdigest()


def _stable_import_timestamp(source_sha256: str, recipe_sha256: str) -> datetime:
    """Derive stable provenance time from immutable source and declaration identity."""
    identity = hashlib.sha256(f"{source_sha256}:{recipe_sha256}".encode()).digest()
    seconds_in_century = 100 * 365 * 24 * 60 * 60
    seconds = int.from_bytes(identity[:8], "big") % seconds_in_century
    return datetime(2000, 1, 1, tzinfo=UTC) + timedelta(seconds=seconds)


def _dataset_identity_sha256(
    *,
    content_sha256: str,
    source_recipe_sha256: str,
    schema_version: str,
    calendar_name: str,
    calendar_version: str,
    code_revision: str,
) -> str:
    identity = {
        "calendar_name": calendar_name,
        "calendar_version": calendar_version,
        "code_revision": code_revision,
        "content_sha256": content_sha256,
        "schema_version": schema_version,
        "source_recipe_sha256": source_recipe_sha256,
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _optional_timestamp_iso(timestamp: pd.Timestamp | None) -> str | None:
    return None if timestamp is None else timestamp.isoformat()


def _build_import_evidence(
    *,
    source: ArchiveSourceDeclaration,
    inspection: ArchiveInspection,
    observed_cadence: dict[str, object],
    member_cadence: list[dict[str, object]],
    expected_groups: set[ExpectedGroup],
    effective_production_symbols: tuple[str, ...],
    source_quality: MinuteBarsQualityAssessment,
    quarantined_groups: tuple[SymbolSessionQuality, ...],
) -> dict[str, object]:
    selected = {member.name: member for member in inspection.members}
    return {
        "schema_version": _EVIDENCE_SCHEMA_VERSION,
        "source_declaration": _source_declaration_record(source),
        "source_sha256": inspection.source_sha256,
        "source_recipe_sha256": _source_recipe_sha256(source),
        "selected_members": [
            {
                "name": name,
                "size": selected[name].size,
                "sha256": selected[name].sha256,
                "columns": list(selected[name].columns),
                "row_estimate": selected[name].row_estimate,
                "min_timestamp": _optional_timestamp_iso(selected[name].min_timestamp),
                "max_timestamp": _optional_timestamp_iso(selected[name].max_timestamp),
                "symbol_count": len(selected[name].symbols),
            }
            for name in sorted(source.member_names)
        ],
        "observed_cadence": observed_cadence,
        "member_cadence": member_cadence,
        "effective_production_symbols": list(effective_production_symbols),
        "expected_production_groups": [
            {"symbol": symbol, "session_date": session_date.isoformat()}
            for symbol, session_date in sorted(expected_groups)
        ],
        "source_quality": source_quality.aggregate.model_dump(mode="json"),
        "source_group_quality": [
            _source_group_quality_record(
                group,
                publication_state=("quarantined" if group.requires_quarantine else "published"),
            )
            for group in source_quality.groups
        ],
        "quarantined_groups": [_quarantine_record(group) for group in quarantined_groups],
    }


def _snapshot_content_files(snapshot_root: Path) -> tuple[Path, ...]:
    return tuple(
        path for path in snapshot_root.rglob("*") if path.is_file() and path.name != "manifest.json"
    )


def import_snapshot(
    archive_path: Path,
    *,
    root: Path,
    source: ArchiveSourceDeclaration,
    limits: ArchiveReadLimits = DEFAULT_ARCHIVE_READ_LIMITS,
) -> tuple[DatasetManifest, Path]:
    """Copy approved legacy bars into a new immutable canonical snapshot."""
    try:
        inspection = inspect_archive(
            archive_path,
            member_names=source.member_names,
            limits=limits,
        )
    except ValueError as error:
        if "requested archive members are not approved" in str(error):
            raise ValueError(
                "declared source members are absent or unapproved: "
                + ",".join(sorted(source.member_names))
            ) from error
        raise
    if not inspection.members:
        raise ValueError("archive contains no approved CSV or Parquet members")

    inspected_members = {member.name: member for member in inspection.members}
    undeclared = sorted(set(source.member_names).difference(inspected_members))
    if undeclared:
        raise ValueError(f"declared source members are absent or unapproved: {undeclared}")
    invalid_schema = [
        name
        for name in source.member_names
        if not _TIINGO_MINUTE_COLUMNS.issubset(inspected_members[name].columns)
    ]
    if invalid_schema:
        raise ValueError(
            "declared source members lack required Tiingo columns: " + ",".join(invalid_schema)
        )

    recipe_hash = _source_recipe_sha256(source)
    imported_at = _stable_import_timestamp(inspection.source_sha256, recipe_hash)
    frames_by_member: dict[str, list[pd.DataFrame]] = {name: [] for name in source.member_names}
    for member_name, frame in iter_archive_member_frames(
        archive_path,
        member_names=source.member_names,
        limits=limits,
    ):
        frames_by_member[member_name].append(frame)
    if not any(frames_by_member.values()):
        raise ValueError("archive contains no tabular rows")
    try:
        post_read_inspection = inspect_archive(
            archive_path,
            member_names=source.member_names,
            limits=limits,
        )
    except (OSError, tarfile.TarError, ValueError) as error:
        raise SnapshotVerificationError(
            "source archive changed after inspection and selected-member read"
        ) from error
    if post_read_inspection.source_sha256 != inspection.source_sha256:
        raise SnapshotVerificationError(
            "source archive changed after inspection and selected-member read"
        )
    initial_member_hashes = {member.name: member.sha256 for member in inspection.members}
    post_read_member_hashes = {
        member.name: member.sha256 for member in post_read_inspection.members
    }
    if post_read_member_hashes != initial_member_hashes:
        raise SnapshotVerificationError("selected archive member changed after inspection and read")
    source_non_monotonic: set[ExpectedGroup] = set()
    member_cadence: list[dict[str, object]] = []
    selected_source_rows: list[pd.DataFrame] = []
    for member_name in sorted(source.member_names):
        member_frames = frames_by_member[member_name]
        if not member_frames:
            raise ValueError(f"declared source member contains no tabular rows: {member_name}")
        member_rows = pd.concat(member_frames, ignore_index=True)
        try:
            member_non_monotonic, cadence = _source_order_and_cadence(member_rows)
        except ValueError as error:
            raise ValueError(f"{member_name}: {error}") from error
        source_non_monotonic.update(member_non_monotonic)
        member_cadence.append({"name": member_name, **cadence})
        selected_source_rows.append(member_rows)
    source_rows = pd.concat(selected_source_rows, ignore_index=True)
    cadence_evidence = {"validated": True, "bar_size": _BAR_SIZE}
    bars = canonicalize_tiingo_rows(source_rows, ingested_at=imported_at)
    if bars.empty:
        raise ValueError("archive contains no minute bars")
    _validate_canonical_symbols(bars)
    _validate_declared_date_range(bars, source)
    effective_production = _effective_production_symbols(bars, source)
    expected_production_groups = _expected_production_groups(source, effective_production)
    expected_source_groups = _expected_source_groups(source, effective_production)
    source_quality = assess_minute_bars(
        bars,
        expected_groups=expected_source_groups,
        production_symbols=effective_production,
        source_non_monotonic_groups=source_non_monotonic,
    )
    failing_production = tuple(
        group for group in source_quality.groups if group.production and not group.passed
    )
    if failing_production:
        raise SnapshotQualityError(
            "production quality gate failed: "
            + ", ".join(f"{group.symbol}/{group.session_date}" for group in failing_production)
        )
    quarantined_groups = tuple(
        group for group in source_quality.groups if group.requires_quarantine
    )
    quarantine_keys = {(group.symbol, group.session_date) for group in quarantined_groups}
    published_bars = bars.loc[
        [
            (symbol, session_date) not in quarantine_keys
            for symbol, session_date in zip(
                bars["symbol"].tolist(),
                bars["session_date"].tolist(),
                strict=True,
            )
        ]
    ].reset_index(drop=True)
    if published_bars.empty:
        raise SnapshotQualityError("all observed robustness groups require quarantine")
    published_quality = assess_minute_bars(
        published_bars,
        expected_groups=expected_production_groups,
        production_symbols=effective_production,
    )
    if not published_quality.passed:
        raise SnapshotQualityError("published bars do not pass the declared quality scope")

    paths = LabPaths.from_root(root)
    calendar_name = "XNYS"
    calendar_version = _package_version("exchange-calendars")
    code_revision = _code_revision(paths.root)
    paths.canonical.mkdir(parents=True, exist_ok=True)

    temporary_root = Path(tempfile.mkdtemp(prefix=".snapshot-", dir=paths.canonical)).resolve()
    final_root: Path | None = None
    try:
        temporary_outputs = _write_partitions(published_bars, temporary_root)
        evidence = _build_import_evidence(
            source=source,
            inspection=inspection,
            observed_cadence=cadence_evidence,
            member_cadence=member_cadence,
            expected_groups=expected_production_groups,
            effective_production_symbols=effective_production,
            source_quality=source_quality,
            quarantined_groups=quarantined_groups,
        )
        evidence_path = _contained_path(temporary_root, "import-evidence.json")
        evidence_path.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        content_hash = _content_sha256(
            temporary_root,
            _snapshot_content_files(temporary_root),
        )
        identity_hash = _dataset_identity_sha256(
            content_sha256=content_hash,
            source_recipe_sha256=recipe_hash,
            schema_version=_SCHEMA_VERSION,
            calendar_name=calendar_name,
            calendar_version=calendar_version,
            code_revision=code_revision,
        )
        dataset_id = f"tiingo-iex-1min-{identity_hash[:32]}"
        final_root = paths.canonical / dataset_id
        manifest = DatasetManifest(
            dataset_id=dataset_id,
            schema_version=_SCHEMA_VERSION,
            source_uri=inspection.archive.as_uri(),
            source_sha256=inspection.source_sha256,
            content_sha256=content_hash,
            code_revision=code_revision,
            calendar_name=calendar_name,
            calendar_version=calendar_version,
            created_at=imported_at,
            provider=source.provider,
            feed=source.feed,
            bar_size=source.bar_size,
            row_count=len(published_bars),
            symbols=tuple(sorted(published_bars["symbol"].unique().tolist())),
            min_timestamp=published_bars["timestamp"].min().to_pydatetime(),
            max_timestamp=published_bars["timestamp"].max().to_pydatetime(),
            quality=published_quality.aggregate,
        )
        manifest_path = _contained_path(temporary_root, "manifest.json")
        manifest_path.write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )
        if sha256_file(inspection.archive) != inspection.source_sha256:
            raise SnapshotVerificationError(
                "source archive changed after inspection and selected-member read"
            )
        if final_root.exists():
            existing_manifest = verify_snapshot(dataset_id, root=paths.root)
            if existing_manifest != manifest:
                raise SnapshotVerificationError(
                    "dataset identity collision with a different immutable snapshot"
                )
            _safe_remove_temporary(temporary_root, paths.canonical)
            existing_outputs = tuple(
                sorted(final_root.rglob("*.parquet"), key=lambda path: path.as_posix())
            )
            if not existing_outputs:
                raise SnapshotVerificationError(
                    "idempotent snapshot contains no Parquet partitions"
                )
            return existing_manifest, existing_outputs[0]
        try:
            temporary_root.rename(final_root)
        except FileExistsError:
            existing_manifest = verify_snapshot(dataset_id, root=paths.root)
            if existing_manifest != manifest:
                raise SnapshotVerificationError(
                    "dataset identity collision with a different immutable snapshot"
                )
            _safe_remove_temporary(temporary_root, paths.canonical)
            existing_outputs = tuple(
                sorted(final_root.rglob("*.parquet"), key=lambda path: path.as_posix())
            )
            if not existing_outputs:
                raise SnapshotVerificationError(
                    "idempotent snapshot contains no Parquet partitions"
                )
            return existing_manifest, existing_outputs[0]
    except BaseException:
        if temporary_root.exists():
            _safe_remove_temporary(temporary_root, paths.canonical)
        raise

    if final_root is None:
        raise RuntimeError("snapshot identity was not computed")
    first_output = final_root / temporary_outputs[0].relative_to(temporary_root)
    return manifest, first_output


def _read_snapshot_bars(files: tuple[Path, ...]) -> pd.DataFrame:
    frames = [cast(pd.DataFrame, pq.ParquetFile(path).read().to_pandas()) for path in files]
    if not frames:
        raise SnapshotVerificationError("snapshot contains no Parquet partitions")
    return pd.concat(frames, ignore_index=True).sort_values(
        ["symbol", "timestamp"], kind="stable", ignore_index=True
    )


def verify_snapshot(dataset_id: str, *, root: Path) -> DatasetManifest:
    """Recompute canonical content hashes, metadata, and quality."""
    paths = LabPaths.from_root(root)
    snapshot_root = paths.canonical / dataset_id
    if snapshot_root.resolve().parent != paths.canonical.resolve():
        raise SnapshotVerificationError("dataset_id must identify one canonical snapshot")
    manifest_path = snapshot_root / "manifest.json"
    if not manifest_path.is_file():
        raise SnapshotVerificationError(f"manifest does not exist: {manifest_path}")
    manifest = DatasetManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    if manifest.dataset_id != dataset_id:
        raise SnapshotVerificationError("manifest dataset_id does not match requested snapshot")

    outputs = tuple(snapshot_root.rglob("*.parquet"))
    content_hash = _content_sha256(
        snapshot_root,
        _snapshot_content_files(snapshot_root),
    )
    if content_hash != manifest.content_sha256:
        raise SnapshotVerificationError("snapshot content hash does not match manifest")

    evidence_path = snapshot_root / "import-evidence.json"
    if not evidence_path.is_file():
        raise SnapshotVerificationError("snapshot import evidence does not exist")
    evidence = cast(
        dict[str, object],
        json.loads(evidence_path.read_text(encoding="utf-8")),
    )
    source_record = cast(dict[str, object], evidence["source_declaration"])
    raw_robustness_groups = cast(
        list[dict[str, object]],
        source_record.get("expected_robustness_groups", []),
    )
    source = ArchiveSourceDeclaration(
        provider=str(source_record["provider"]),
        feed=str(source_record["feed"]),
        bar_size=str(source_record["bar_size"]),
        member_names=tuple(cast(list[str], source_record["member_names"])),
        production_symbols=tuple(cast(list[str], source_record["production_symbols"])),
        expected_start_date=date.fromisoformat(str(source_record["expected_start_date"])),
        expected_end_date=date.fromisoformat(str(source_record["expected_end_date"])),
        expected_robustness_groups=tuple(
            (
                str(raw_group["symbol"]),
                date.fromisoformat(str(raw_group["session_date"])),
            )
            for raw_group in raw_robustness_groups
        ),
    )
    recipe_hash = _source_recipe_sha256(source)
    if evidence.get("source_recipe_sha256") != recipe_hash:
        raise SnapshotVerificationError("source declaration recipe hash does not match evidence")
    if evidence.get("source_sha256") != manifest.source_sha256:
        raise SnapshotVerificationError("source hash evidence does not match manifest")
    raw_selected_members = evidence.get("selected_members")
    if not isinstance(raw_selected_members, list):
        raise SnapshotVerificationError("selected member hash evidence is missing")
    selected_names: list[str] = []
    for raw_member in raw_selected_members:
        if not isinstance(raw_member, dict):
            raise SnapshotVerificationError("selected member hash evidence is invalid")
        name = raw_member.get("name")
        member_hash = raw_member.get("sha256")
        if (
            not isinstance(name, str)
            or not isinstance(member_hash, str)
            or re.fullmatch(r"[0-9a-f]{64}", member_hash) is None
        ):
            raise SnapshotVerificationError("selected member hash evidence is invalid")
        selected_names.append(name)
    if selected_names != sorted(source.member_names):
        raise SnapshotVerificationError(
            "selected member hash evidence does not match source declaration"
        )
    source_group_quality = evidence.get("source_group_quality")
    if not isinstance(source_group_quality, list):
        raise SnapshotVerificationError("complete source group-quality evidence is missing")
    evidenced_groups = {
        (str(record.get("symbol")), date.fromisoformat(str(record.get("session_date"))))
        for record in source_group_quality
        if isinstance(record, dict)
    }
    missing_robustness_evidence = set(source.expected_robustness_groups).difference(
        evidenced_groups
    )
    if missing_robustness_evidence:
        raise SnapshotVerificationError(
            "source group-quality evidence omits declared robustness groups"
        )
    expected_dataset_id = (
        "tiingo-iex-1min-"
        + _dataset_identity_sha256(
            content_sha256=manifest.content_sha256,
            source_recipe_sha256=recipe_hash,
            schema_version=manifest.schema_version,
            calendar_name=manifest.calendar_name,
            calendar_version=manifest.calendar_version,
            code_revision=manifest.code_revision,
        )[:32]
    )
    if dataset_id != expected_dataset_id:
        raise SnapshotVerificationError(
            "dataset_id does not match canonical content and declared identities"
        )
    stable_imported_at = _stable_import_timestamp(manifest.source_sha256, recipe_hash)
    if manifest.created_at != stable_imported_at:
        raise SnapshotVerificationError("manifest created_at is not deterministic")
    bars = _read_snapshot_bars(outputs)
    effective_production = _effective_production_symbols(bars, source)
    quality = assess_minute_bars(
        bars,
        expected_groups=_expected_production_groups(source, effective_production),
        production_symbols=effective_production,
    )
    observed = {
        "bar_size": _BAR_SIZE,
        "provider": str(bars["provider"].iloc[0]),
        "feed": str(bars["feed"].iloc[0]),
        "row_count": len(bars),
        "symbols": tuple(sorted(bars["symbol"].unique().tolist())),
        "min_timestamp": bars["timestamp"].min().to_pydatetime(),
        "max_timestamp": bars["timestamp"].max().to_pydatetime(),
        "quality": quality.aggregate,
        "created_at": bars["ingested_at"].iloc[0].to_pydatetime(),
    }
    expected = {
        key: getattr(manifest, key)
        for key in (
            "bar_size",
            "provider",
            "feed",
            "row_count",
            "symbols",
            "min_timestamp",
            "max_timestamp",
            "quality",
            "created_at",
        )
    }
    if observed != expected:
        raise SnapshotVerificationError(
            "snapshot metadata or quality does not match manifest: "
            + json.dumps(
                {key: str(value) for key, value in observed.items() if value != expected[key]},
                sort_keys=True,
            )
        )
    return manifest
