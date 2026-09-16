"""Causal listing-lifecycle state derived from validated Polygon snapshots."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

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
            merged = candidates.merge(
                source,
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
    permitted = bool(
        eligible_rows > 0
        and mapped_rows + exception_rows == eligible_rows
        and coverage_ratio == 1.0
        and all(item["coverage_ratio"] == 1.0 for item in monthly)
    )
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
        "missing_data_policy": "preserve_nulls_no_fill_no_inference",
        "provider_splicing": "FORBIDDEN",
        "order_route": "FORBIDDEN",
        "rejection_reasons": [] if permitted else ["BLOCKED_LIFECYCLE_COVERAGE"],
        "strategy_evaluation_permitted": permitted,
        "paper_activation": False,
    }
    return mapping, audit
