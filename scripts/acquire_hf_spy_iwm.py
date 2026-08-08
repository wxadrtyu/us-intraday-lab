from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date
from pathlib import Path

import pandas as pd

from us_intraday_lab.long_horizon.hf_source import aggregate_hf_regular_minutes

REPO_ID = "mito0o852/OHLCV-1m"
REPO_TYPE = "dataset"
REVISION = "main"
SYMBOLS = ("SPY", "IWM")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _months(start: str, end: str) -> tuple[str, ...]:
    first = date.fromisoformat(start + "-01")
    last = date.fromisoformat(end + "-01")
    if first > last:
        raise ValueError("start month must not exceed end month")
    values: list[str] = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        values.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year += 1
            month = 1
    return tuple(values)


def acquire_month(month: str, *, root: Path) -> dict[str, object]:
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    from huggingface_hub import hf_hub_download

    root = root.resolve()
    staging = (root / "data" / "staging" / "hf_ohlcv_1m").resolve()
    output_dir = (root / "data" / "raw" / "hf_spy_iwm_5min").resolve()
    manifest_dir = (root / "data" / "catalog" / "hf_spy_iwm_5min" / "months").resolve()
    for directory in (staging, output_dir, manifest_dir):
        directory.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"spy-iwm-{month}.parquet"
    manifest_path = manifest_dir / f"spy-iwm-{month}.json"
    if output.is_file() and manifest_path.is_file():
        retained = json.loads(manifest_path.read_text(encoding="utf-8"))
        if retained["output_sha256"] != _sha256(output):
            raise ValueError(f"retained output hash mismatch for {month}")
        return retained

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
    if staging not in source.parents:
        raise RuntimeError("downloaded source escaped the declared staging directory")
    source_sha256 = _sha256(source)
    selected = pd.read_parquet(source, filters=[("ticker", "in", list(SYMBOLS))])
    result = aggregate_hf_regular_minutes(selected, symbols=SYMBOLS)
    if not result.accepted_sessions:
        raise ValueError(f"month {month} contains no complete shared sessions")
    temporary = output.with_suffix(".tmp.parquet")
    result.bars.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(output)
    record: dict[str, object] = {
        "accepted_sessions": [value.isoformat() for value in result.accepted_sessions],
        "bar_size": "5min",
        "month": month,
        "output_path": output.as_posix(),
        "output_rows": len(result.bars),
        "output_sha256": _sha256(output),
        "provider": "huggingface",
        "rejected_sessions": [value.isoformat() for value in result.rejected_sessions],
        "repository": REPO_ID,
        "revision": REVISION,
        "source_filename": filename,
        "source_sha256": source_sha256,
        "symbols": list(SYMBOLS),
    }
    temporary_manifest = manifest_path.with_suffix(".tmp")
    temporary_manifest.write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary_manifest.replace(manifest_path)
    source.unlink()
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--start-month", required=True)
    parser.add_argument("--end-month", required=True)
    args = parser.parse_args()
    for month in _months(args.start_month, args.end_month):
        result = acquire_month(month, root=args.root)
        print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
