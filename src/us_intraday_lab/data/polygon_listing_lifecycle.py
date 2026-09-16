"""Causal listing-lifecycle state derived from validated Polygon snapshots."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from us_intraday_lab.data.polygon_historical_master import (
    POLYGON_REFERENCE_NAMESPACE,
    load_historical_master_validation,
)


@dataclass(frozen=True, slots=True)
class SnapshotLineage:
    asof: date
    parquet_path: str
    manifest_path: str
    content_sha256: str
    rows: int


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_ticker(value: object) -> str:
    """Normalize an exact Polygon/Alpaca ticker without Unicode folding."""
    ticker = str(value).strip()
    if not ticker or not ticker.isascii():
        raise ValueError("LIFECYCLE_TICKER_NOT_ASCII")
    return ticker.upper()


def lifecycle_bucket(*, tenure: int, left_censored: bool) -> str:
    """Assign the frozen lifecycle bucket from elapsed observed months."""
    if tenure < 0:
        raise ValueError("LIFECYCLE_TENURE_NEGATIVE")
    if left_censored:
        return "left_censored"
    if tenure <= 3:
        return "new_0_3"
    if tenure <= 12:
        return "young_4_12"
    if tenure <= 36:
        return "maturing_13_36"
    return "seasoned_37_plus"


def _asof_from_directory(path: Path) -> date:
    try:
        return date.fromisoformat(path.name.removeprefix("asof="))
    except ValueError as error:
        raise ValueError("LIFECYCLE_SNAPSHOT_ASOF_INVALID") from error


def _load_snapshot(directory: Path) -> tuple[pd.DataFrame, SnapshotLineage]:
    asof = _asof_from_directory(directory)
    parquet = directory / "tickers.parquet"
    manifest_path = directory / "manifest.json"
    if not parquet.is_file() or not manifest_path.is_file():
        raise ValueError("LIFECYCLE_SNAPSHOT_PAIR_MISSING")
    try:
        manifest = json.loads(manifest_path.read_text("utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("LIFECYCLE_SNAPSHOT_MANIFEST_INVALID") from error
    digest = _sha256(parquet)
    if manifest.get("content_sha256") != digest:
        raise ValueError("LIFECYCLE_SNAPSHOT_HASH_MISMATCH")
    expected = {
        "source_namespace": POLYGON_REFERENCE_NAMESPACE,
        "provider": "polygon",
        "asof": asof.isoformat(),
        "missing_data_policy": "preserve_nulls_no_fill_no_inference",
        "provider_splicing": "FORBIDDEN",
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("LIFECYCLE_SNAPSHOT_PROVENANCE_FAILURE")
    frame = pd.read_parquet(parquet, columns=["ticker", "active", "asof"])
    if len(frame) != manifest.get("row_count"):
        raise ValueError("LIFECYCLE_SNAPSHOT_ROW_COUNT_MISMATCH")
    if frame.empty:
        raise ValueError("LIFECYCLE_SNAPSHOT_EMPTY")
    parsed_asof = pd.to_datetime(frame["asof"], errors="coerce").dt.date
    if parsed_asof.isna().any() or not parsed_asof.eq(asof).all():
        raise ValueError("LIFECYCLE_SNAPSHOT_ASOF_MISMATCH")
    if frame["active"].isna().any():
        raise ValueError("LIFECYCLE_ACTIVE_MISSING")
    frame = frame.assign(
        ticker=frame["ticker"].astype(str).str.strip(),
        ticker_normalized=frame["ticker"].map(normalize_ticker),
        snapshot_asof=asof,
        active=frame["active"].astype(bool),
        snapshot_sha256=digest,
    )
    if frame.duplicated(["ticker", "active"]).any():
        raise ValueError("LIFECYCLE_DUPLICATE_TICKER_ACTIVITY")
    if frame.duplicated("ticker_normalized", keep=False).any():
        raise ValueError("LIFECYCLE_NORMALIZATION_COLLISION")
    lineage = SnapshotLineage(
        asof=asof,
        parquet_path=str(parquet.resolve()),
        manifest_path=str(manifest_path.resolve()),
        content_sha256=digest,
        rows=len(frame),
    )
    return frame, lineage


def _elapsed_months(first: date, current: date) -> int:
    return (current.year - first.year) * 12 + current.month - first.month


def derive_lifecycle_history(
    *, root: Path, validation_path: Path
) -> tuple[pd.DataFrame, tuple[SnapshotLineage, ...]]:
    """Derive lifecycle state using only each snapshot's causal history prefix."""
    load_historical_master_validation(validation_path.resolve())
    snapshots_root = (
        root.resolve()
        / "data"
        / "staging"
        / POLYGON_REFERENCE_NAMESPACE
        / "snapshots"
    )
    directories = sorted(snapshots_root.glob("asof=*"), key=_asof_from_directory)
    if not directories:
        raise RuntimeError("LIFECYCLE_SNAPSHOTS_MISSING")

    first_snapshot = _asof_from_directory(directories[0])
    first_active: dict[str, date] = {}
    previous_active: dict[str, bool] = {}
    rows: list[pd.DataFrame] = []
    lineage: list[SnapshotLineage] = []
    for directory in directories:
        snapshot, snapshot_lineage = _load_snapshot(directory)
        current_rows: list[dict[str, object]] = []
        for row in snapshot.itertuples(index=False):
            ticker = str(row.ticker)
            normalized = str(row.ticker_normalized)
            asof = row.snapshot_asof
            active = bool(row.active)
            if active and normalized not in first_active:
                first_active[normalized] = asof
            observed_first = first_active.get(normalized)
            left_censored = bool(active and observed_first == first_snapshot)
            tenure = (
                _elapsed_months(observed_first, asof)
                if active and observed_first is not None
                else None
            )
            current_rows.append(
                {
                    "ticker": ticker,
                    "ticker_normalized": normalized,
                    "snapshot_asof": asof,
                    "active": active,
                    "first_observed_active_month": observed_first,
                    "active_tenure_months": tenure,
                    "left_censored": left_censored,
                    "reactivated_this_month": bool(
                        active and previous_active.get(normalized) is False
                    ),
                    "lifecycle_bucket": (
                        lifecycle_bucket(tenure=tenure, left_censored=left_censored)
                        if tenure is not None
                        else None
                    ),
                    "snapshot_sha256": row.snapshot_sha256,
                }
            )
        previous_active = dict(
            zip(snapshot["ticker_normalized"], snapshot["active"], strict=True)
        )
        rows.append(pd.DataFrame.from_records(current_rows))
        lineage.append(snapshot_lineage)
    return pd.concat(rows, ignore_index=True), tuple(lineage)
