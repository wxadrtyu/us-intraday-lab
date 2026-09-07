from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expected_stems(events: pd.DataFrame, batch_size: int) -> dict[tuple[date, int, str], int]:
    result: dict[tuple[date, int, str], int] = {}
    events = events.copy()
    events["month"] = events["session_date"].map(lambda value: value.replace(day=1))
    for month, month_rows in events.groupby("month", observed=True, sort=True):
        union = tuple(sorted(month_rows["symbol"].astype(str).unique()))
        for bar_idx in sorted(month_rows["bar_idx"].astype(int).unique()):
            slot = month_rows.loc[month_rows["bar_idx"].eq(bar_idx)]
            for offset in range(0, len(union), batch_size):
                batch = union[offset : offset + batch_size]
                identity = hashlib.sha256(",".join(batch).encode()).hexdigest()[:16]
                stem = f"bar-{bar_idx:02d}-batch-{offset // batch_size:04d}-{identity}"
                count = int(slot["symbol"].astype(str).isin(batch).sum())
                result[(month, bar_idx, stem)] = count
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--start", default="2021-01-01", type=date.fromisoformat)
    parser.add_argument("--end", default="2026-03-31", type=date.fromisoformat)
    parser.add_argument("--batch-size", default=50, type=int)
    args = parser.parse_args()

    events = pd.read_parquet(args.events, columns=["symbol", "session_date", "bar_idx"])
    events["session_date"] = pd.to_datetime(events["session_date"]).dt.date
    events = events.loc[events["session_date"].between(args.start, args.end)].drop_duplicates()
    expected = expected_stems(events, args.batch_size)
    staging = args.root / "data" / "staging" / "alpaca_sip_quote_features_v1"
    actual_manifests = set(staging.glob("????-??/*.json"))
    canonical_manifests: list[Path] = []
    missing_artifacts: list[str] = []
    hash_failures: list[str] = []
    row_count_failures: list[str] = []
    frames: list[pd.DataFrame] = []
    for (month, bar_idx, stem), expected_rows in expected.items():
        manifest_path = staging / month.strftime("%Y-%m") / f"{stem}.json"
        parquet_path = manifest_path.with_suffix(".parquet")
        canonical_manifests.append(manifest_path)
        if not manifest_path.is_file() or not parquet_path.is_file():
            missing_artifacts.append(str(manifest_path))
            continue
        manifest: dict[str, Any] = json.loads(manifest_path.read_text("utf-8"))
        if manifest.get("content_sha256") != sha256_file(parquet_path):
            hash_failures.append(str(parquet_path))
            continue
        frame = pd.read_parquet(parquet_path)
        if int(manifest.get("requested_rows", -1)) != len(frame) or len(frame) != expected_rows:
            row_count_failures.append(str(parquet_path))
        frame["bar_idx"] = bar_idx
        frames.append(frame)

    canonical_set = set(canonical_manifests)
    extra_manifests = sorted(str(path) for path in actual_manifests.difference(canonical_set))
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    keys = ["symbol", "session_date", "bar_idx"]
    duplicate_keys = int(combined.duplicated(keys, keep=False).sum()) if not combined.empty else 0
    available = combined["quote_available"].astype(bool) if not combined.empty else pd.Series(dtype=bool)
    quote_time = pd.to_datetime(combined.get("timestamp"), utc=True)
    decision_time = pd.to_datetime(combined.get("decision_timestamp"), utc=True)
    noncausal_rows = int((available & quote_time.ge(decision_time)).sum())
    unexpected_keys = 0
    missing_keys = len(events)
    if not combined.empty:
        expected_index = pd.MultiIndex.from_frame(events[keys])
        actual_index = pd.MultiIndex.from_frame(combined[keys])
        unexpected_keys = int((~actual_index.isin(expected_index)).sum())
        missing_keys = int((~expected_index.isin(actual_index)).sum())
    passed = not any(
        (missing_artifacts, hash_failures, row_count_failures)
    ) and duplicate_keys == 0 and noncausal_rows == 0 and unexpected_keys == 0 and missing_keys == 0

    cache = args.root / "research" / "cache" / "us_market_event_quote_features_v1.parquet"
    cache.parent.mkdir(parents=True, exist_ok=True)
    if passed:
        temporary = cache.with_suffix(".tmp.parquet")
        combined.sort_values(keys, kind="stable").to_parquet(
            temporary, index=False, compression="zstd"
        )
        os.replace(temporary, cache)
    result = {
        "schema_version": "1.0.0",
        "status": "COMPLETE" if passed else "FAILED_CLOSED",
        "protocol_id": "us-market-event-quotes-v1",
        "start": args.start.isoformat(),
        "end": args.end.isoformat(),
        "expected_event_rows": len(events),
        "actual_event_rows": len(combined),
        "available_rows": int(available.sum()),
        "missing_quote_rows": int((~available).sum()),
        "availability_rate": float(available.mean()),
        "expected_shards": len(expected),
        "canonical_shards": len(canonical_manifests) - len(missing_artifacts),
        "extra_probe_shards_excluded": len(extra_manifests),
        "missing_artifacts": missing_artifacts,
        "hash_failures": hash_failures,
        "row_count_failures": row_count_failures,
        "duplicate_key_rows": duplicate_keys,
        "missing_event_keys": missing_keys,
        "unexpected_event_keys": unexpected_keys,
        "noncausal_quote_rows": noncausal_rows,
        "cache_path": str(cache) if passed else None,
        "cache_sha256": sha256_file(cache) if passed else None,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
    markdown = args.report.with_suffix(".md")
    markdown.write_text(
        "# US market SIP quote feature audit\n\n"
        f"- Status: `{result['status']}`\n"
        f"- Event rows: {result['actual_event_rows']:,} / {result['expected_event_rows']:,}\n"
        f"- Quote availability: {result['available_rows']:,} "
        f"({result['availability_rate']:.4%})\n"
        f"- Explicit missing quotes: {result['missing_quote_rows']:,}\n"
        f"- Canonical shards: {result['canonical_shards']:,} / {result['expected_shards']:,}\n"
        f"- Noncanonical one-day probe shards excluded: "
        f"{result['extra_probe_shards_excluded']:,}\n"
        f"- Duplicate keys: {result['duplicate_key_rows']:,}\n"
        f"- Missing keys: {result['missing_event_keys']:,}\n"
        f"- Noncausal quote rows: {result['noncausal_quote_rows']:,}\n",
        "utf-8",
    )
    print(json.dumps(result, sort_keys=True), flush=True)
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
