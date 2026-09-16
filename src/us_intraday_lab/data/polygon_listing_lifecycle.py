"""Causal listing-lifecycle state derived from validated Polygon snapshots."""

from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from importlib.metadata import version
from pathlib import Path
from typing import Any
from uuid import uuid4

import exchange_calendars as xcals  # type: ignore[import-untyped]
import pandas as pd

from us_intraday_lab.data.polygon_historical_master import (
    POLYGON_REFERENCE_NAMESPACE,
    load_historical_master_validation,
)

_XNYS = xcals.get_calendar("XNYS")
_MAPPING_COLUMNS = (
    "month",
    "symbol",
    "ticker_normalized",
    "normalization_collision",
    "snapshot_asof",
    "active",
    "first_observed_active_month",
    "active_tenure_months",
    "left_censored",
    "reactivated_this_month",
    "lifecycle_bucket",
    "snapshot_sha256",
    "universe_dataset_id",
    "information_cutoff",
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
    frame["normalization_collision"] = frame.duplicated(
        "ticker_normalized", keep=False
    )
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
            if active and ticker not in first_active:
                first_active[ticker] = asof
            observed_first = first_active.get(ticker)
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
                    "normalization_collision": bool(row.normalization_collision),
                    "snapshot_asof": asof,
                    "active": active,
                    "first_observed_active_month": observed_first,
                    "active_tenure_months": tenure,
                    "left_censored": left_censored,
                    "reactivated_this_month": bool(
                        active and previous_active.get(ticker) is False
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
            zip(snapshot["ticker"], snapshot["active"], strict=True)
        )
        rows.append(pd.DataFrame.from_records(current_rows))
        lineage.append(snapshot_lineage)
    return pd.concat(rows, ignore_index=True), tuple(lineage)


def _decisions_path(root: Path) -> tuple[Path, dict[str, Any]]:
    catalog = root.resolve() / "data" / "catalog" / "monthly_universe_sip_v2"
    candidates: list[tuple[Path, dict[str, Any]]] = []
    for manifest_path in catalog.glob("*/manifest.json"):
        try:
            manifest = json.loads(manifest_path.read_text("utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("LIFECYCLE_UNIVERSE_MANIFEST_INVALID") from error
        if (
            manifest.get("start_month") == "2018-04-01"
            and manifest.get("end_month") == "2026-03-01"
        ):
            candidates.append((manifest_path.parent / "decisions.parquet", manifest))
    if len(candidates) != 1:
        raise RuntimeError(f"LIFECYCLE_UNIVERSE_AMBIGUOUS:{len(candidates)}")
    decisions_path, manifest = candidates[0]
    if (
        not decisions_path.is_file()
        or manifest.get("content_sha256") != _sha256(decisions_path)
        or not manifest.get("dataset_id")
    ):
        raise RuntimeError("LIFECYCLE_UNIVERSE_HASH_MISMATCH")
    return decisions_path, manifest


def first_xnys_session(month: date) -> date:
    """Return the first official XNYS session in a calendar month."""
    end = (pd.Timestamp(month) + pd.offsets.MonthEnd(0)).date()
    sessions = _XNYS.sessions_in_range(pd.Timestamp(month), pd.Timestamp(end))
    if sessions.empty:
        raise RuntimeError("LIFECYCLE_XNYS_MONTH_EMPTY")
    return sessions[0].date()


def select_cutoff(asofs: Sequence[date], first_session: date) -> date:
    """Select the latest source snapshot strictly before a decision month."""
    eligible = [value for value in asofs if value < first_session]
    if not eligible:
        raise RuntimeError("LIFECYCLE_PRIOR_SNAPSHOT_MISSING")
    return max(eligible)


def _exception(*, month: date, symbol: str, reason: str) -> dict[str, str]:
    return {"month": month.isoformat(), "symbol": symbol, "reason": reason}


def build_lifecycle_coverage(
    *, root: Path, validation_path: Path
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Map every eligible symbol to one causal lifecycle row and audit coverage."""
    validation = load_historical_master_validation(validation_path.resolve())
    history, lineage = derive_lifecycle_history(
        root=root, validation_path=validation_path
    )
    decisions_path, universe_manifest = _decisions_path(root)
    decisions = pd.read_parquet(
        decisions_path,
        columns=["symbol", "month", "eligible", "information_cutoff"],
    )
    decisions = decisions.loc[decisions["eligible"].eq(True)].copy()
    decisions["symbol"] = decisions["symbol"].astype(str).str.strip()
    decisions["month"] = pd.to_datetime(decisions["month"], errors="raise").dt.date
    decisions["information_cutoff"] = pd.to_datetime(
        decisions["information_cutoff"], errors="raise"
    ).dt.date
    decisions["ticker_normalized"] = decisions["symbol"].map(normalize_ticker)
    decisions = decisions.sort_values(["month", "symbol"], kind="stable").reset_index(
        drop=True
    )

    asofs = tuple(item.asof for item in lineage)
    mapping_parts: list[pd.DataFrame] = []
    exceptions: list[dict[str, str]] = []
    monthly: list[dict[str, object]] = []
    source_collision_frame = history.loc[
        history["normalization_collision"].eq(True),
        ["snapshot_asof", "ticker", "ticker_normalized", "active"],
    ].sort_values(["snapshot_asof", "ticker_normalized", "ticker"], kind="stable")
    source_collisions = [
        {
            "snapshot_asof": row.snapshot_asof.isoformat(),
            "ticker": str(row.ticker),
            "ticker_normalized": str(row.ticker_normalized),
            "active": bool(row.active),
        }
        for row in source_collision_frame.itertuples(index=False)
    ]
    for month, eligible in decisions.groupby("month", sort=True):
        month_date = month if isinstance(month, date) else pd.Timestamp(month).date()
        denominator = len(eligible)
        month_exceptions: list[dict[str, str]] = []
        collision = eligible.duplicated("ticker_normalized", keep=False)
        if collision.any():
            month_exceptions.extend(
                _exception(
                    month=month_date,
                    symbol=str(row.symbol),
                    reason="NORMALIZATION_COLLISION",
                )
                for row in eligible.loc[collision].itertuples(index=False)
            )
        candidates = eligible.loc[~collision].copy()
        try:
            cutoff = select_cutoff(asofs, first_xnys_session(month_date))
        except RuntimeError:
            month_exceptions.extend(
                _exception(
                    month=month_date,
                    symbol=str(row.symbol),
                    reason="CUTOFF_NOT_CAUSAL",
                )
                for row in candidates.itertuples(index=False)
            )
            candidates = candidates.iloc[0:0]
            cutoff = None

        month_mapping = pd.DataFrame(columns=_MAPPING_COLUMNS)
        if cutoff is not None and not candidates.empty:
            source = history.loc[history["snapshot_asof"].eq(cutoff)].copy()
            collision_norms = set(
                source.loc[
                    source["normalization_collision"].eq(True), "ticker_normalized"
                ]
            )
            source_collision = candidates["ticker_normalized"].isin(collision_norms)
            month_exceptions.extend(
                _exception(
                    month=month_date,
                    symbol=str(row.symbol),
                    reason="NORMALIZATION_COLLISION",
                )
                for row in candidates.loc[source_collision].itertuples(index=False)
            )
            merged = candidates.loc[~source_collision].merge(
                source.loc[source["normalization_collision"].eq(False)],
                how="left",
                on="ticker_normalized",
                validate="one_to_one",
                suffixes=("_decision", "_polygon"),
            )
            unmatched = merged["ticker"].isna()
            missing_state = (~unmatched) & (
                merged["active"].ne(True) | merged["lifecycle_bucket"].isna()
            )
            month_exceptions.extend(
                _exception(
                    month=month_date,
                    symbol=str(row.symbol),
                    reason="UNMATCHED",
                )
                for row in merged.loc[unmatched].itertuples(index=False)
            )
            month_exceptions.extend(
                _exception(
                    month=month_date,
                    symbol=str(row.symbol),
                    reason="MISSING_LIFECYCLE_STATE",
                )
                for row in merged.loc[missing_state].itertuples(index=False)
            )
            valid = merged.loc[~unmatched & ~missing_state].copy()
            valid["month"] = month_date
            valid["universe_dataset_id"] = str(universe_manifest["dataset_id"])
            month_mapping = valid.loc[:, _MAPPING_COLUMNS]
            mapping_parts.append(month_mapping)
        mapped = len(month_mapping)
        exceptions.extend(month_exceptions)
        monthly.append(
            {
                "month": month_date.isoformat(),
                "eligible_rows": denominator,
                "mapped_rows": mapped,
                "exception_rows": len(month_exceptions),
                "coverage_ratio": mapped / denominator if denominator else 0.0,
                "snapshot_asof": cutoff.isoformat() if cutoff is not None else None,
            }
        )

    mapping = (
        pd.concat(mapping_parts, ignore_index=True)
        if mapping_parts
        else pd.DataFrame(columns=_MAPPING_COLUMNS)
    )
    mapping = mapping.sort_values(["month", "symbol"], kind="stable").reset_index(
        drop=True
    )
    exceptions.sort(key=lambda row: (row["month"], row["symbol"], row["reason"]))
    eligible_rows = len(decisions)
    mapped_rows = len(mapping)
    exception_rows = len(exceptions)
    coverage_ratio = mapped_rows / eligible_rows if eligible_rows else 0.0
    source_collision_rows = len(source_collisions)
    coverage_complete = bool(
        eligible_rows > 0
        and mapped_rows + exception_rows == eligible_rows
        and coverage_ratio == 1.0
        and all(item["coverage_ratio"] == 1.0 for item in monthly)
    )
    permitted = coverage_complete and source_collision_rows == 0
    rejection_reasons: list[str] = []
    if not coverage_complete:
        rejection_reasons.append("BLOCKED_LIFECYCLE_COVERAGE")
    if source_collision_rows:
        rejection_reasons.append("BLOCKED_LIFECYCLE_NORMALIZATION_COLLISION")
    audit: dict[str, object] = {
        "schema_version": "1.0.0",
        "contract": "polygon-listing-lifecycle-coverage-v1",
        "historical_master_validation_report_sha256": validation[
            "validation_report_sha256"
        ],
        "universe_dataset_id": universe_manifest["dataset_id"],
        "universe_sha256": universe_manifest["content_sha256"],
        "snapshot_lineage": [
            {
                "asof": item.asof.isoformat(),
                "content_sha256": item.content_sha256,
                "rows": item.rows,
            }
            for item in lineage
        ],
        "months": len(monthly),
        "eligible_rows": eligible_rows,
        "mapped_rows": mapped_rows,
        "exception_rows": exception_rows,
        "coverage_ratio": coverage_ratio,
        "monthly_coverage": monthly,
        "exceptions": exceptions,
        "source_normalization_collision_rows": source_collision_rows,
        "source_normalization_collisions": source_collisions,
        "missing_data_policy": "preserve_nulls_no_fill_no_inference",
        "provider_splicing": "FORBIDDEN",
        "order_route": "FORBIDDEN",
        "rejection_reasons": rejection_reasons,
        "strategy_evaluation_permitted": permitted,
        "paper_activation": False,
    }
    return mapping, audit


def _catalog_result(directory: Path, manifest: dict[str, object]) -> dict[str, object]:
    result = dict(manifest)
    result["mapping_path"] = str((directory / "lifecycle.parquet").resolve())
    result["exceptions_path"] = str((directory / "exceptions.parquet").resolve())
    result["manifest_path"] = str((directory / "manifest.json").resolve())
    return result


def _validate_existing_catalog(
    directory: Path, *, dataset_id: str
) -> dict[str, object]:
    manifest_path = directory / "manifest.json"
    mapping_path = directory / "lifecycle.parquet"
    exceptions_path = directory / "exceptions.parquet"
    try:
        manifest = json.loads(manifest_path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("LIFECYCLE_CATALOG_COLLISION") from error
    valid = (
        manifest.get("dataset_id") == dataset_id
        and mapping_path.is_file()
        and exceptions_path.is_file()
        and manifest.get("mapping_sha256") == _sha256(mapping_path)
        and manifest.get("exceptions_sha256") == _sha256(exceptions_path)
    )
    if not valid:
        raise RuntimeError("LIFECYCLE_CATALOG_COLLISION")
    return _catalog_result(directory, manifest)


def publish_lifecycle_catalog(
    *, root: Path, validation_path: Path
) -> dict[str, object]:
    """Publish or validate a hash-addressed immutable lifecycle catalog."""
    mapping, audit = build_lifecycle_coverage(
        root=root, validation_path=validation_path
    )
    identity_payload = {
        "contract": audit["contract"],
        "historical_master_validation_report_sha256": audit[
            "historical_master_validation_report_sha256"
        ],
        "universe_dataset_id": audit["universe_dataset_id"],
        "universe_sha256": audit["universe_sha256"],
        "snapshot_lineage": audit["snapshot_lineage"],
        "calendar": f"XNYS@{version('exchange-calendars')}",
    }
    identity = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:24]
    dataset_id = f"polygon-listing-lifecycle-v1-{identity}"
    parent = root.resolve() / "data" / "catalog" / "polygon_listing_lifecycle_v1"
    directory = parent / dataset_id
    if directory.exists():
        return _validate_existing_catalog(directory, dataset_id=dataset_id)

    parent.mkdir(parents=True, exist_ok=True)
    temporary = parent / f".{dataset_id}.{uuid4().hex}.tmp"
    temporary.mkdir()
    mapping_path = temporary / "lifecycle.parquet"
    exceptions_path = temporary / "exceptions.parquet"
    try:
        mapping.to_parquet(mapping_path, index=False, compression="zstd")
        exceptions = pd.DataFrame.from_records(
            audit["exceptions"], columns=["month", "symbol", "reason"]
        )
        exceptions.to_parquet(exceptions_path, index=False, compression="zstd")
        manifest: dict[str, object] = {
            **audit,
            "dataset_id": dataset_id,
            "calendar": identity_payload["calendar"],
            "mapping_file": mapping_path.name,
            "mapping_sha256": _sha256(mapping_path),
            "exceptions_file": exceptions_path.name,
            "exceptions_sha256": _sha256(exceptions_path),
            "exception_reason_counts": dict(
                sorted(Counter(exceptions["reason"]).items())
            ),
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(directory)
    except Exception:
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    return _catalog_result(directory, manifest)
