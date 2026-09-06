"""Resume-safe minute acquisition for every point-in-time eligible symbol-month."""

from __future__ import annotations

import calendar
import hashlib
import json
import re
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd

from us_intraday_lab.data.alpaca_iex_acquisition import (
    BLIND_CUTOFF,
    ReadOnlyAlpacaIexDownloader,
    assess_acquired_bars,
)

INVALID_SYMBOL_RESPONSE = re.compile(r"invalid symbol:\s*([^\"}]+)", re.IGNORECASE)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def acquire_eligible_minutes(
    *,
    root: Path,
    decisions_path: Path,
    downloader: ReadOnlyAlpacaIexDownloader,
    batch_size: int = 25,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, object]]:
    decisions = pd.read_parquet(decisions_path)
    decisions["month"] = pd.to_datetime(decisions["month"]).dt.date
    eligible = decisions.loc[decisions["eligible"].astype(bool), ["month", "symbol"]]
    output_root = root.resolve() / "data" / "staging" / "alpaca_iex_1min_dynamic"
    output_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for month, month_rows in eligible.groupby("month", observed=True, sort=True):
        month = cast(date, month)
        end = date(month.year, month.month, calendar.monthrange(month.year, month.month)[1])
        symbols = tuple(sorted(set(month_rows["symbol"].astype(str))))
        month_root = output_root / month.strftime("%Y-%m")
        month_root.mkdir(exist_ok=True)
        for offset in range(0, len(symbols), batch_size):
            batch = symbols[offset : offset + batch_size]
            identity = hashlib.sha256(",".join(batch).encode()).hexdigest()[:16]
            stem = f"batch-{offset // batch_size:04d}-{identity}"
            parquet = month_root / f"{stem}.parquet"
            manifest_path = month_root / f"{stem}.json"
            if parquet.is_file() and manifest_path.is_file():
                record = cast(dict[str, object], json.loads(manifest_path.read_text("utf-8")))
                if record["content_sha256"] != _sha256_file(parquet):
                    raise ValueError(f"minute shard hash mismatch: {parquet}")
                records.append(record)
                continue
            if parquet.exists() or manifest_path.exists():
                raise ValueError(f"partial minute shard requires audit: {month}/{stem}")
            rejected: list[str] = []
            remaining = list(batch)
            attempt = 0
            while remaining:
                try:
                    bars = downloader.fetch(symbols=tuple(sorted(remaining)), start=month, end=end)
                    break
                except Exception as error:  # bounded provider retry
                    invalid = INVALID_SYMBOL_RESPONSE.search(str(error))
                    if invalid and invalid.group(1).strip().upper() in remaining:
                        symbol = invalid.group(1).strip().upper()
                        remaining.remove(symbol)
                        rejected.append(symbol)
                        continue
                    if attempt == 4:
                        raise
                    sleep(min(30.0, 2.0**attempt))
                    attempt += 1
            else:
                bars = pd.DataFrame()
            temporary = parquet.with_suffix(".tmp.parquet")
            bars.to_parquet(temporary, index=False, compression="zstd")
            temporary.replace(parquet)
            quality: dict[str, object] | None = None
            if not bars.empty:
                quality = assess_acquired_bars(
                    bars, symbols=tuple(sorted(remaining)), start=month, end=end
                )
                quality.pop("groups", None)
            record = {
                "schema_version": "1.0.0",
                "provider": "alpaca",
                "feed": "iex",
                "bar_size": "1min",
                "adjustment": "split",
                "month": month.isoformat(),
                "end": end.isoformat(),
                "symbols": list(batch),
                "provider_rejected_symbols": sorted(rejected),
                "row_count": len(bars),
                "quality": quality,
                "blind_test_candidate": month >= BLIND_CUTOFF,
                "strategy_metrics_permitted": month < BLIND_CUTOFF,
                "content_sha256": _sha256_file(parquet),
            }
            temporary_manifest = manifest_path.with_suffix(".tmp")
            temporary_manifest.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n", "utf-8"
            )
            temporary_manifest.replace(manifest_path)
            records.append(record)
    return records
