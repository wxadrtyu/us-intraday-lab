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

import numpy as np
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


def quarantine_invalid_symbol_sessions(
    bars: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, str]]]:
    """Quarantine a complete symbol-session when any constituent bar is corrupt."""
    if bars.empty:
        return bars.copy(), bars.copy(), []
    numeric = bars.loc[:, ["open", "high", "low", "close", "volume"]]
    invalid = pd.Series(
        ~np.isfinite(numeric.to_numpy(dtype="float64")).all(axis=1), index=bars.index
    )
    invalid |= numeric[["open", "high", "low", "close"]].le(0).any(axis=1)
    invalid |= numeric["high"].lt(numeric[["open", "low", "close"]].max(axis=1))
    invalid |= numeric["low"].gt(numeric[["open", "high", "close"]].min(axis=1))
    invalid |= numeric["volume"].lt(0)
    invalid |= bars.duplicated(["symbol", "timestamp"], keep=False)
    ordered = bars.sort_values(["symbol", "timestamp"])
    ordered_invalid = (ordered["high"] / ordered["low"] - 1.0).gt(0.50)
    invalid.loc[ordered.index] |= ordered_invalid
    if "trade_count" in bars.columns:
        values = bars["trade_count"].to_numpy(dtype="float64")
        invalid |= ~np.isfinite(values) | (values < 0)
    if "vwap" in bars.columns:
        values = bars["vwap"].to_numpy(dtype="float64")
        invalid |= ~np.isfinite(values) | (values <= 0)
    bad_keys = bars.loc[invalid, ["symbol", "session_date"]].drop_duplicates()
    if bad_keys.empty:
        return bars.copy(), bars.iloc[0:0].copy(), []
    bad_index = pd.MultiIndex.from_frame(bad_keys)
    row_index = pd.MultiIndex.from_frame(bars[["symbol", "session_date"]])
    quarantined_mask = row_index.isin(bad_index)
    evidence = [
        {"symbol": str(row.symbol), "session_date": row.session_date.isoformat()}
        for row in bad_keys.itertuples(index=False)
    ]
    return (
        bars.loc[~quarantined_mask].copy().reset_index(drop=True),
        bars.loc[quarantined_mask].copy().reset_index(drop=True),
        evidence,
    )


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
            quarantine_path = month_root / f"{stem}.quarantine.parquet"
            recovered_path = month_root / f"{stem}.unvalidated.parquet"
            if parquet.is_file() and manifest_path.is_file():
                record = cast(dict[str, object], json.loads(manifest_path.read_text("utf-8")))
                if record["content_sha256"] != _sha256_file(parquet):
                    raise ValueError(f"minute shard hash mismatch: {parquet}")
                quarantine_hash = record.get("quarantine_sha256")
                if quarantine_hash and (
                    not quarantine_path.is_file()
                    or quarantine_hash != _sha256_file(quarantine_path)
                ):
                    raise ValueError(f"minute quarantine hash mismatch: {quarantine_path}")
                records.append(record)
                continue
            recovered_unvalidated_sha256: str | None = None
            if parquet.is_file() and not manifest_path.exists():
                if recovered_path.exists():
                    raise ValueError(f"duplicate unvalidated recovery requires audit: {stem}")
                parquet.replace(recovered_path)
                recovered_unvalidated_sha256 = _sha256_file(recovered_path)
                bars = pd.read_parquet(recovered_path)
            elif manifest_path.exists() or quarantine_path.exists() or recovered_path.exists():
                raise ValueError(f"partial minute shard requires audit: {month}/{stem}")
            else:
                rejected = []
                remaining = list(batch)
                attempt = 0
                while remaining:
                    try:
                        bars = downloader.fetch(
                            symbols=tuple(sorted(remaining)), start=month, end=end
                        )
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
            if recovered_unvalidated_sha256 is not None:
                rejected = []
                remaining = list(batch)
            accepted, quarantined, quarantined_groups = quarantine_invalid_symbol_sessions(bars)
            temporary = parquet.with_suffix(".tmp.parquet")
            accepted.to_parquet(temporary, index=False, compression="zstd")
            temporary.replace(parquet)
            quarantine_sha256: str | None = None
            if not quarantined.empty:
                temporary_quarantine = quarantine_path.with_suffix(".tmp.parquet")
                quarantined.to_parquet(temporary_quarantine, index=False, compression="zstd")
                temporary_quarantine.replace(quarantine_path)
                quarantine_sha256 = _sha256_file(quarantine_path)
            quality: dict[str, object] | None = None
            if not accepted.empty:
                quality = assess_acquired_bars(
                    accepted,
                    symbols=tuple(sorted(remaining)),
                    start=month,
                    end=end,
                    allow_adjusted_jumps=True,
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
                "row_count": len(accepted),
                "quarantined_rows": len(quarantined),
                "quarantined_symbol_sessions": quarantined_groups,
                "quarantine_sha256": quarantine_sha256,
                "recovered_unvalidated_sha256": recovered_unvalidated_sha256,
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
