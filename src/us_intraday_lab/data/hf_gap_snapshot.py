from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from datetime import UTC, date, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import cast

import pandas as pd


def quarantine_duplicate_symbol_sessions(
    bars: pd.DataFrame,
) -> tuple[pd.DataFrame, tuple[tuple[str, date], ...], int]:
    """Remove whole symbol-sessions containing duplicate minute identities."""
    duplicate_rows = bars.duplicated(["symbol", "timestamp"], keep=False)
    groups: tuple[tuple[str, date], ...] = tuple(
        sorted(
            {
                (str(row.symbol), cast(date, row.session_date))
                for row in bars.loc[
                    duplicate_rows, ["symbol", "session_date"]
                ].itertuples(index=False)
            }
        )
    )
    if not groups:
        return bars, groups, int(duplicate_rows.sum())
    quarantine = pd.MultiIndex.from_tuples(groups, names=["symbol", "session_date"])
    row_groups = pd.MultiIndex.from_frame(bars[["symbol", "session_date"]])
    retained = bars.loc[~row_groups.isin(quarantine)].copy().reset_index(drop=True)
    return retained, groups, int(duplicate_rows.sum())


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_hash(root: Path, files: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(bytes.fromhex(sha256_file(path)))
        digest.update(b"\0")
    return digest.hexdigest()


def _package_version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "unknown"


def _code_revision(repo: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def _load_month_records(root: Path, months: tuple[str, ...]) -> list[dict[str, object]]:
    catalog = root / "data" / "catalog" / "hf_finnhub_gap_1min" / "months"
    records: list[dict[str, object]] = []
    for month in months:
        matches = sorted(catalog.glob(f"{month}-*.json"))
        if len(matches) != 1:
            raise ValueError(f"expected one immutable month manifest for {month}, found {len(matches)}")
        record = cast(dict[str, object], json.loads(matches[0].read_text("utf-8")))
        source = Path(str(record["output_path"])).resolve()
        if not source.is_file() or sha256_file(source) != record["output_sha256"]:
            raise ValueError(f"month output failed hash verification: {month}")
        records.append(record)
    return records


def _quality_summary(records: list[dict[str, object]]) -> dict[str, object]:
    qualities = [cast(dict[str, object], record["quality"]) for record in records]
    quarantined = [
        {"month": record["month"], **cast(dict[str, object], group)}
        for record, quality in zip(records, qualities, strict=True)
        for group in cast(list[object], quality.get("quarantined_duplicate_groups", []))
    ]
    summed = {
        key: sum(cast(int, quality.get(key, 0)) for quality in qualities)
        for key in (
            "expected_minutes",
            "observed_minutes",
            "missing_minutes",
            "duplicate_rows",
            "invalid_ohlcv_rows",
            "outside_session_rows",
            "cadence_misaligned_rows",
            "adjusted_jump_rows",
            "intrabar_range_anomaly_rows",
            "source_outside_session_rows_filtered",
            "source_duplicate_rows",
        )
    }
    return {
        **summed,
        "complete": summed["missing_minutes"] == 0,
        "structural_quality_passed": all(
            summed[key] == 0
            for key in (
                "duplicate_rows",
                "invalid_ohlcv_rows",
                "outside_session_rows",
                "cadence_misaligned_rows",
            )
        ),
        "adjusted_price_anomaly_passed": all(
            bool(quality["adjusted_price_anomaly_passed"]) for quality in qualities
        ),
        "quarantined_duplicate_groups": quarantined,
        "no_fill_policy": True,
    }


def verify_hf_gap_snapshot(snapshot_root: Path) -> dict[str, object]:
    snapshot_root = snapshot_root.resolve()
    manifest = cast(
        dict[str, object], json.loads((snapshot_root / "manifest.json").read_text("utf-8"))
    )
    if snapshot_root.name != manifest["dataset_id"]:
        raise ValueError("snapshot directory does not match dataset identity")
    files = [path for path in snapshot_root.rglob("*") if path.is_file()]
    content_files = [path for path in files if path.name != "manifest.json"]
    if not content_files or content_hash(snapshot_root, content_files) != manifest["content_sha256"]:
        raise ValueError("snapshot content hash mismatch")
    identity_fields = (
        "content_sha256",
        "provider",
        "feed",
        "bar_size",
        "adjustment",
        "calendar",
        "calendar_version",
        "code_revision",
        "window",
        "symbols",
    )
    identity = {field: manifest[field] for field in identity_fields}
    expected = "hf-finnhub-1min-" + hashlib.sha256(
        _canonical_json(identity).encode()
    ).hexdigest()[:32]
    if manifest["dataset_id"] != expected:
        raise ValueError("snapshot manifest identity mismatch")
    return manifest


def publish_hf_gap_snapshot(
    *, repo: Path, root: Path, label: str, months: tuple[str, ...]
) -> dict[str, object]:
    root = root.resolve()
    repo = repo.resolve()
    records = _load_month_records(root, months)
    quality = _quality_summary(records)
    canonical = root / "data" / "lake" / "acquired_hf"
    canonical.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".hf-finnhub-", dir=canonical)).resolve()
    try:
        data_dir = temporary / "months"
        data_dir.mkdir()
        month_evidence: list[dict[str, object]] = []
        for record in records:
            month = str(record["month"])
            source = Path(str(record["output_path"])).resolve()
            target = data_dir / f"{month}.parquet"
            shutil.copy2(source, target)
            month_evidence.append(
                {
                    "month": month,
                    "source_filename": record["source_filename"],
                    "source_sha256": record["source_sha256"],
                    "output_sha256": record["output_sha256"],
                    "output_rows": record["output_rows"],
                }
            )
        evidence = {
            "schema_version": "1.0.0",
            "provider": "huggingface",
            "feed": "finnhub-derived",
            "repository": records[0]["repository"],
            "revision": records[0]["revision"],
            "source_separation": "not blended with Alpaca IEX snapshots",
            "adjustment": "source-as-published; split-anomaly-gated",
            "calendar": "XNYS",
            "no_fill_policy": True,
            "months": month_evidence,
            "quality": quality,
        }
        evidence_path = temporary / "quality-evidence.json"
        evidence_path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", "utf-8")
        content_files = [path for path in temporary.rglob("*") if path.is_file()]
        content_sha256 = content_hash(temporary, content_files)
        symbols = tuple(cast(list[str], records[0]["symbols"]))
        identity = {
            "content_sha256": content_sha256,
            "provider": "huggingface",
            "feed": "finnhub-derived",
            "bar_size": "1min",
            "adjustment": "source-as-published; split-anomaly-gated",
            "calendar": "XNYS",
            "calendar_version": _package_version("exchange-calendars"),
            "code_revision": _code_revision(repo),
            "window": {"label": label, "start_month": months[0], "end_month": months[-1]},
            "symbols": list(symbols),
        }
        dataset_id = "hf-finnhub-1min-" + hashlib.sha256(
            _canonical_json(identity).encode()
        ).hexdigest()[:32]
        created_at = max(
            datetime.fromtimestamp(
                Path(str(record["output_path"])).stat().st_mtime, tz=UTC
            )
            for record in records
        )
        manifest = {
            "schema_version": "1.0.0",
            "dataset_id": dataset_id,
            **identity,
            "created_at": created_at.isoformat(),
            "row_count": sum(cast(int, record["output_rows"]) for record in records),
            "min_timestamp": min(str(record["min_timestamp"]) for record in records),
            "max_timestamp": max(str(record["max_timestamp"]) for record in records),
            "quality_complete": bool(quality["complete"]),
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", "utf-8"
        )
        final = canonical / dataset_id
        if final.exists():
            retained = verify_hf_gap_snapshot(final)
            shutil.rmtree(temporary)
            return retained
        temporary.rename(final)
        return verify_hf_gap_snapshot(final)
    except BaseException:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
