from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import cast

import pandas as pd
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from us_intraday_lab.contracts.datasets import DatasetManifest
from us_intraday_lab.data.archive import inspect_archive, iter_archive_frames
from us_intraday_lab.data.canonicalize import canonicalize_tiingo_rows
from us_intraday_lab.data.quality import assess_minute_bars
from us_intraday_lab.settings import LabPaths

_BAR_SIZE = "1min"
_SCHEMA_VERSION = "1.0.0"
_TIINGO_MINUTE_COLUMNS = frozenset(
    {"ticker", "date", "open", "high", "low", "close", "volume"}
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


def _write_partitions(bars: pd.DataFrame, snapshot_root: Path) -> tuple[Path, ...]:
    outputs: list[Path] = []
    grouped = bars.groupby(["session_date", "symbol"], sort=True, observed=True)
    for (session_date, symbol), group in grouped:
        partition = (
            snapshot_root
            / f"bar_size={_BAR_SIZE}"
            / f"session_date={session_date}"
            / f"symbol={symbol}"
        )
        partition.mkdir(parents=True)
        output = partition / "part-00000.parquet"
        group.reset_index(drop=True).to_parquet(output, index=False)
        outputs.append(output)
    return tuple(outputs)


def _safe_remove_temporary(path: Path, parent: Path) -> None:
    resolved_parent = parent.resolve()
    resolved_path = path.resolve()
    if resolved_path.parent != resolved_parent or not resolved_path.name.startswith(".snapshot-"):
        raise RuntimeError(f"refusing to remove unverified temporary directory: {path}")
    shutil.rmtree(resolved_path)


def import_snapshot(archive_path: Path, *, root: Path) -> tuple[DatasetManifest, Path]:
    """Copy approved legacy bars into a new immutable canonical snapshot."""
    inspection = inspect_archive(archive_path)
    if not inspection.members:
        raise ValueError("archive contains no approved CSV or Parquet members")

    minute_members = tuple(
        member.name
        for member in inspection.members
        if _TIINGO_MINUTE_COLUMNS.issubset(member.columns)
    )
    if not minute_members:
        raise ValueError(
            "archive contains no Tiingo minute-bar member with required columns: "
            + ",".join(sorted(_TIINGO_MINUTE_COLUMNS))
        )

    imported_at = datetime.now(UTC)
    source_frames = list(iter_archive_frames(archive_path, member_names=minute_members))
    if not source_frames:
        raise ValueError("archive contains no tabular rows")
    source = pd.concat(source_frames, ignore_index=True)
    bars = canonicalize_tiingo_rows(source, ingested_at=imported_at)
    if bars.empty:
        raise ValueError("archive contains no minute bars")
    quality = assess_minute_bars(bars)
    if not quality.passed:
        failing_production = [
            f"{group.symbol}/{group.session_date}"
            for group in quality.groups
            if group.production and not group.passed
        ]
        raise SnapshotQualityError(
            "production quality gate failed: " + ", ".join(failing_production)
        )

    paths = LabPaths.from_root(root)
    dataset_id = f"tiingo-iex-1min-{inspection.source_sha256[:16]}"
    final_root = paths.canonical / dataset_id
    paths.canonical.mkdir(parents=True, exist_ok=True)
    if final_root.exists():
        raise FileExistsError(f"immutable snapshot already exists: {final_root}")

    temporary_root = Path(
        tempfile.mkdtemp(prefix=".snapshot-", dir=paths.canonical)
    ).resolve()
    try:
        temporary_outputs = _write_partitions(bars, temporary_root)
        content_hash = _content_sha256(temporary_root, temporary_outputs)
        manifest = DatasetManifest(
            dataset_id=dataset_id,
            schema_version=_SCHEMA_VERSION,
            source_uri=inspection.archive.as_uri(),
            source_sha256=inspection.source_sha256,
            content_sha256=content_hash,
            code_revision=_code_revision(paths.root),
            calendar_name="XNYS",
            calendar_version=_package_version("exchange-calendars"),
            created_at=imported_at,
            provider="tiingo",
            feed="iex",
            bar_size=_BAR_SIZE,
            row_count=len(bars),
            symbols=tuple(sorted(bars["symbol"].unique().tolist())),
            min_timestamp=bars["timestamp"].min().to_pydatetime(),
            max_timestamp=bars["timestamp"].max().to_pydatetime(),
            quality=quality.aggregate,
        )
        (temporary_root / "manifest.json").write_text(
            manifest.model_dump_json(indent=2),
            encoding="utf-8",
        )
        temporary_root.rename(final_root)
    except BaseException:
        if temporary_root.exists():
            _safe_remove_temporary(temporary_root, paths.canonical)
        raise

    first_output = final_root / temporary_outputs[0].relative_to(temporary_root)
    return manifest, first_output


def _read_snapshot_bars(files: tuple[Path, ...]) -> pd.DataFrame:
    frames = [
        cast(pd.DataFrame, pq.ParquetFile(path).read().to_pandas()) for path in files
    ]
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
    content_hash = _content_sha256(snapshot_root, outputs)
    if content_hash != manifest.content_sha256:
        raise SnapshotVerificationError("snapshot content hash does not match manifest")

    bars = _read_snapshot_bars(outputs)
    quality = assess_minute_bars(bars)
    observed = {
        "bar_size": _BAR_SIZE,
        "provider": str(bars["provider"].iloc[0]),
        "feed": str(bars["feed"].iloc[0]),
        "row_count": len(bars),
        "symbols": tuple(sorted(bars["symbol"].unique().tolist())),
        "min_timestamp": bars["timestamp"].min().to_pydatetime(),
        "max_timestamp": bars["timestamp"].max().to_pydatetime(),
        "quality": quality.aggregate,
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
        )
    }
    if observed != expected:
        raise SnapshotVerificationError(
            "snapshot metadata or quality does not match manifest: "
            + json.dumps(
                {
                    key: str(value)
                    for key, value in observed.items()
                    if value != expected[key]
                },
                sort_keys=True,
            )
        )
    return manifest
