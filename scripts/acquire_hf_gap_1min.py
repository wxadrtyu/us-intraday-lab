from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast

import pandas as pd

from us_intraday_lab.data.alpaca_iex_acquisition import (  # type: ignore[import-untyped]
    DEFAULT_SYMBOLS,
    assess_acquired_bars,
    restrict_to_xnys_regular_grid,
)
from us_intraday_lab.data.hf_gap_snapshot import quarantine_duplicate_symbol_sessions

REPO_ID = "mito0o852/OHLCV-1m"
REPO_TYPE = "dataset"
REVISION = "main"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _months(start: str, end: str) -> tuple[str, ...]:
    first = date.fromisoformat(start + "-01")
    last = date.fromisoformat(end + "-01")
    values: list[str] = []
    cursor = first
    while cursor <= last:
        values.append(cursor.strftime("%Y-%m"))
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    return tuple(values)


def _bounds(month: str) -> tuple[date, date]:
    start = date.fromisoformat(month + "-01")
    next_month = date(start.year + (start.month == 12), start.month % 12 + 1, 1)
    return start, next_month - pd.Timedelta(days=1)


def acquire_month(month: str, *, root: Path, symbols: tuple[str, ...]) -> dict[str, object]:
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from huggingface_hub import hf_hub_download

    root = root.resolve()
    output_dir = root / "data" / "raw" / "hf_finnhub_gap_1min"
    catalog_dir = root / "data" / "catalog" / "hf_finnhub_gap_1min" / "months"
    staging = root / "data" / "staging" / "hf_ohlcv_1m_gap"
    for directory in (output_dir, catalog_dir, staging):
        directory.mkdir(parents=True, exist_ok=True)
    retained = sorted(catalog_dir.glob(f"{month}-*.json"))
    if retained:
        retained_record = cast(dict[str, object], json.loads(retained[-1].read_text("utf-8")))
        output = Path(str(retained_record["output_path"]))
        if output.is_file() and _sha256(output) == retained_record["output_sha256"]:
            return retained_record
        raise ValueError(f"retained HF gap month failed hash verification: {month}")

    filename = f"data/ohlcv_{month}.parquet"
    source = Path(
        hf_hub_download(
            repo_id=REPO_ID,
            repo_type=REPO_TYPE,
            filename=filename,
            revision=REVISION,
            local_dir=staging,
        )
    ).resolve()
    source_sha256 = _sha256(source)
    selected = pd.read_parquet(source, filters=[("ticker", "in", list(symbols))])
    selected = selected.rename(columns={"ticker": "symbol"})
    selected["timestamp"] = pd.to_datetime(selected["timestamp"], utc=True, errors="raise")
    selected["session_date"] = selected["timestamp"].dt.tz_convert("America/New_York").dt.date
    selected["provider"] = "huggingface"
    selected["feed"] = "finnhub-derived"
    selected["ingested_at"] = datetime.now(UTC)
    selected, filtered = restrict_to_xnys_regular_grid(selected)
    selected, quarantined_duplicate_groups, source_duplicate_rows = (
        quarantine_duplicate_symbol_sessions(selected)
    )
    start, end = _bounds(month)
    quality = assess_acquired_bars(selected, symbols=symbols, start=start, end=end)
    quality["source_outside_session_rows_filtered"] = filtered
    quality["source_duplicate_rows"] = source_duplicate_rows
    quality["quarantined_duplicate_groups"] = [
        {"symbol": symbol, "session_date": session.isoformat()}
        for symbol, session in quarantined_duplicate_groups
    ]
    temporary = output_dir / f".{month}.tmp.parquet"
    selected.to_parquet(temporary, index=False, compression="zstd")
    output_sha256 = _sha256(temporary)
    output = output_dir / f"{month}-{output_sha256[:16]}.parquet"
    if output.exists() and _sha256(output) != output_sha256:
        raise ValueError(f"HF gap output identity collision: {month}")
    if output.exists():
        temporary.unlink()
    else:
        temporary.replace(output)
    record: dict[str, object] = {
        "schema_version": "1.0.0",
        "provider": "huggingface",
        "feed": "finnhub-derived",
        "repository": REPO_ID,
        "revision": REVISION,
        "source_filename": filename,
        "source_sha256": source_sha256,
        "adjustment": "source-as-published; split-anomaly-gated",
        "bar_size": "1min",
        "month": month,
        "symbols": list(symbols),
        "output_path": output.as_posix(),
        "output_sha256": output_sha256,
        "output_rows": len(selected),
        "min_timestamp": pd.Timestamp(selected["timestamp"].min()).isoformat(),
        "max_timestamp": pd.Timestamp(selected["timestamp"].max()).isoformat(),
        "quality": quality,
    }
    manifest = catalog_dir / f"{month}-{output_sha256[:16]}.json"
    temporary_manifest = manifest.with_suffix(".tmp")
    temporary_manifest.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", "utf-8")
    temporary_manifest.replace(manifest)
    source.unlink()
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--start-month", default="2018-10")
    parser.add_argument("--end-month", default="2020-12")
    args = parser.parse_args()
    symbols = tuple(sorted(DEFAULT_SYMBOLS))
    for month in _months(args.start_month, args.end_month):
        record = acquire_month(month, root=args.root, symbols=symbols)
        print(json.dumps({"month": month, "rows": record["output_rows"]}), flush=True)


if __name__ == "__main__":
    main()
