"""Audit a bounded training-only Alpaca News metadata probe."""

from __future__ import annotations

import argparse
import json
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from us_intraday_lab.data.news_event_acquisition import (
    CANONICAL_COLUMNS,
    TRAINING_END,
    TRAINING_START,
    _sha256_file,
)

FORBIDDEN_COLUMNS = frozenset({"content", "author", "images", "url"})
TRAINING_DAY_COUNT = (TRAINING_END - TRAINING_START).days + 1


def audit_probe(*, root: Path, start: date, end: date) -> dict[str, object]:
    if start > end or start < TRAINING_START or end > TRAINING_END:
        raise ValueError("ALPACA_NEWS_AUDIT_TRAINING_ONLY")
    staging = root / "data/staging/alpaca_news_metadata_v1"
    missing_days: list[str] = []
    partial_days: list[str] = []
    hash_failures: list[str] = []
    contract_failures: list[str] = []
    frames: list[pd.DataFrame] = []
    page_count = 0
    symbol_links = 0
    current = start
    while current <= end:
        base = staging / current.strftime("%Y-%m") / current.isoformat()
        parquet = base.with_suffix(".parquet")
        manifest_path = base.with_suffix(".json")
        if not parquet.exists() and not manifest_path.exists():
            missing_days.append(current.isoformat())
            current += timedelta(days=1)
            continue
        if not parquet.is_file() or not manifest_path.is_file():
            partial_days.append(current.isoformat())
            current += timedelta(days=1)
            continue
        manifest: dict[str, Any] = json.loads(manifest_path.read_text("utf-8"))
        if manifest.get("complete") is not True:
            partial_days.append(current.isoformat())
            current += timedelta(days=1)
            continue
        if manifest.get("content_sha256") != _sha256_file(parquet):
            hash_failures.append(current.isoformat())
            current += timedelta(days=1)
            continue
        if (
            manifest.get("provider") != "alpaca"
            or manifest.get("source_type") != "historical_news_metadata"
            or manifest.get("available_time_field") != "updated_at"
            or manifest.get("training_only") is not True
        ):
            contract_failures.append(current.isoformat())
        frame = pd.read_parquet(parquet)
        if set(frame.columns) != set(CANONICAL_COLUMNS):
            contract_failures.append(current.isoformat())
        if FORBIDDEN_COLUMNS.intersection(frame.columns):
            contract_failures.append(current.isoformat())
        if not frame.empty:
            available = pd.to_datetime(frame["available_at"], utc=True, errors="coerce")
            day_start = pd.Timestamp(current, tz="UTC")
            if available.isna().any() or not available.between(
                day_start, day_start + pd.Timedelta(days=1), inclusive="left"
            ).all():
                contract_failures.append(current.isoformat())
            if frame["news_id"].astype(str).duplicated().any():
                contract_failures.append(current.isoformat())
            symbol_links += int(frame["symbols"].map(len).sum())
        if int(manifest.get("row_count", -1)) != len(frame):
            contract_failures.append(current.isoformat())
        page_count += int(manifest.get("page_count", 0))
        frames.append(frame)
        current += timedelta(days=1)

    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    duplicate_news_ids = (
        int(combined["news_id"].astype(str).duplicated().sum())
        if not combined.empty
        else 0
    )
    observed_days = (end - start).days + 1
    estimated_full_calls = (
        math.ceil(page_count / observed_days * TRAINING_DAY_COUNT)
        if observed_days and page_count
        else 0
    )
    failures = (
        len(missing_days)
        + len(partial_days)
        + len(hash_failures)
        + len(contract_failures)
        + duplicate_news_ids
    )
    return {
        "schema_version": "1.0.0",
        "status": "COMPLETE" if failures == 0 else "FAILED",
        "provider": "alpaca",
        "source_type": "historical_news_metadata",
        "available_time_field": "updated_at",
        "training_only": True,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "observed_days": observed_days,
        "page_count": page_count,
        "row_count": len(combined),
        "unique_news_ids": (
            int(combined["news_id"].astype(str).nunique()) if not combined.empty else 0
        ),
        "symbol_links": symbol_links,
        "missing_days": len(missing_days),
        "partial_days": len(partial_days),
        "hash_failures": len(hash_failures),
        "contract_failures": len(contract_failures),
        "duplicate_news_ids": duplicate_news_ids,
        "estimated_full_calls": estimated_full_calls,
        "strategy_metrics_permitted": False,
    }


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--json", required=True, type=Path)
    parser.add_argument("--markdown", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    result = audit_probe(
        root=arguments.root.resolve(),
        start=arguments.start,
        end=arguments.end,
    )
    arguments.json.parent.mkdir(parents=True, exist_ok=True)
    arguments.markdown.parent.mkdir(parents=True, exist_ok=True)
    arguments.json.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    arguments.markdown.write_text(
        "# Alpaca News training-only probe\n\n"
        f"- Status: {result['status']}\n"
        f"- UTC days: {result['observed_days']}\n"
        f"- Pages: {result['page_count']}\n"
        f"- Unique news IDs: {result['unique_news_ids']}\n"
        f"- Symbol links: {result['symbol_links']}\n"
        f"- Estimated 2021-2023 calls: {result['estimated_full_calls']}\n"
        f"- Partial days: {result['partial_days']}\n",
        encoding="utf-8",
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "COMPLETE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
