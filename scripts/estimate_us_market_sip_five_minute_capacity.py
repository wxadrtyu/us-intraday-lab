from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import time
from datetime import date, datetime
from pathlib import Path
from typing import cast

import exchange_calendars  # type: ignore[import-untyped]
import pandas as pd

from us_intraday_lab.data.alpaca_sip_five_minute import (
    SIP_FIVE_MINUTE_NAMESPACE,
    ReadOnlyAlpacaSipFiveMinuteDownloader,
    acquire_sip_five_minute_shards,
    load_frozen_candidate_symbols,
    validate_sip_five_minute_source,
)
from us_intraday_lab.data.sip_five_minute_capacity import (
    estimate_capacity,
    resolve_pilot_elapsed_seconds,
    select_liquidity_decile_sample,
)

_XNYS = exchange_calendars.get_calendar("XNYS")


def _liquidity_scores(
    *, daily_source: Path, session: date, candidate_symbols: tuple[str, ...]
) -> pd.Series:
    paths = sorted(daily_source.glob(f"{session:%Y-%m}-*.parquet"))
    if not paths:
        raise ValueError(f"no daily SIP partitions for pilot month {session:%Y-%m}")
    frames = [
        pd.read_parquet(path, columns=["symbol", "timestamp", "close", "volume"])
        for path in paths
    ]
    bars = pd.concat(frames, ignore_index=True)
    timestamps = pd.to_datetime(bars["timestamp"], utc=True, errors="raise")
    bars = bars.loc[
        timestamps.dt.tz_convert("America/New_York").dt.date.eq(session)
    ].copy()
    bars["dollar_volume"] = bars["close"] * bars["volume"]
    observed = bars.groupby("symbol", sort=False)["dollar_volume"].sum()
    return observed.reindex(candidate_symbols, fill_value=0.0).astype(float)


def _month_count(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + end.month - start.month + 1


def _daily_source_identity(*, daily_source: Path, session: date) -> dict[str, object]:
    paths = sorted(daily_source.glob(f"{session:%Y-%m}-*.parquet"))
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.name.encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return {
        "path": str(daily_source.resolve()),
        "monthly_partition_count": len(paths),
        "monthly_partitions_sha256": digest.hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run an isolated representative SIP five-minute capacity pilot."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--production-root", required=True, type=Path)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--protocol", required=True, type=Path)
    parser.add_argument("--daily-source", required=True, type=Path)
    parser.add_argument("--session", required=True, type=date.fromisoformat)
    parser.add_argument("--production-start", required=True, type=date.fromisoformat)
    parser.add_argument("--production-end", required=True, type=date.fromisoformat)
    parser.add_argument("--production-batch-size", default=100, type=int)
    parser.add_argument("--parallel-workers", default=4, type=int)
    parser.add_argument("--maximum-completion-hours", default=168.0, type=float)
    parser.add_argument("--sample-per-decile", default=10, type=int)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()

    symbols = load_frozen_candidate_symbols(
        assets_path=args.assets, protocol_path=args.protocol
    )
    scores = _liquidity_scores(
        daily_source=args.daily_source, session=args.session, candidate_symbols=symbols
    )
    sample = select_liquidity_decile_sample(
        scores=scores, per_decile=args.sample_per_decile
    )
    args.root.mkdir(parents=True, exist_ok=True)
    namespace = args.root.resolve() / "data" / "staging" / SIP_FIVE_MINUTE_NAMESPACE
    reused_existing_partitions = any(namespace.glob("*.parquet"))
    previous_report: dict[str, object] = {}
    if reused_existing_partitions and args.result.is_file():
        previous_report = cast(
            dict[str, object], json.loads(args.result.read_text("utf-8"))
        )
    started = time.perf_counter()
    records = acquire_sip_five_minute_shards(
        root=args.root,
        downloader=ReadOnlyAlpacaSipFiveMinuteDownloader.from_environment(),
        symbols=sample,
        start=args.session,
        end=args.session,
        batch_size=len(sample),
    )
    validation = validate_sip_five_minute_source(
        root=args.root,
        symbols=sample,
        start=args.session,
        end=args.session,
        batch_size=len(sample),
    )
    validation_elapsed_seconds = time.perf_counter() - started
    sample_hash = hashlib.sha256("\n".join(sample).encode()).hexdigest()
    partition_set_hash = hashlib.sha256(
        "\n".join(
            f"{record['global_shard_index']}:{record['content_sha256']}"
            for record in sorted(
                records, key=lambda item: int(item["global_shard_index"])
            )
        ).encode()
    ).hexdigest()
    pilot_identity = {
        "pilot_root": str(args.root.resolve()),
        "pilot_session": args.session.isoformat(),
        "sample_symbols_sha256": sample_hash,
        "pilot_partition_set_sha256": partition_set_hash,
    }
    elapsed_seconds = resolve_pilot_elapsed_seconds(
        reused_existing_partitions=reused_existing_partitions,
        validation_elapsed_seconds=validation_elapsed_seconds,
        pilot_identity=pilot_identity,
        previous_report=previous_report,
    )

    parquet_bytes = sum(path.stat().st_size for path in namespace.glob("*.parquet"))
    manifest_bytes = sum(
        path.stat().st_size
        for path in namespace.glob("*.json")
        if path.name != "acquisition_contract.json"
    )
    sessions = _XNYS.sessions_in_range(
        pd.Timestamp(args.production_start), pd.Timestamp(args.production_end)
    )
    expected_symbol_sessions = len(symbols) * len(sessions)
    if not args.production_root.is_dir():
        raise ValueError("production root must already exist for disk-capacity audit")
    free_bytes = shutil.disk_usage(args.production_root).free
    capacity = estimate_capacity(
        sampled_rows=int(validation["rows"]),
        sampled_bytes=parquet_bytes,
        sampled_symbols=len(sample),
        sampled_sessions=1,
        expected_symbol_sessions=expected_symbol_sessions,
        free_bytes=free_bytes,
        sampled_elapsed_seconds=elapsed_seconds,
        parallel_workers=args.parallel_workers,
        maximum_completion_seconds=args.maximum_completion_hours * 3600,
    )
    expected_partitions = _month_count(
        args.production_start, args.production_end
    ) * math.ceil(len(symbols) / args.production_batch_size)
    estimated_manifest_bytes = math.ceil(
        manifest_bytes / len(records) * expected_partitions
    )
    estimated_total_bytes = int(capacity["estimated_bytes"]) + estimated_manifest_bytes
    worst_case_total_bytes = int(capacity["worst_case_bytes"]) + estimated_manifest_bytes
    capacity["estimated_partition_count"] = expected_partitions
    capacity["estimated_manifest_bytes"] = estimated_manifest_bytes
    capacity["estimated_total_bytes"] = estimated_total_bytes
    capacity["worst_case_total_bytes"] = worst_case_total_bytes
    capacity["disk_safe"] = (
        worst_case_total_bytes <= int(capacity["launch_limit_bytes"])
    )
    capacity["safe_to_launch"] = bool(capacity["disk_safe"]) and bool(
        capacity["time_safe"]
    )

    selected_scores = scores.loc[list(sample)]
    all_deciles = pd.qcut(scores.rank(method="first"), q=10, labels=False).astype(int)
    selected_deciles = all_deciles.loc[list(sample)]
    decile_counts = selected_deciles.value_counts().sort_index()
    pilot_bars = pd.concat(
        [pd.read_parquet(path, columns=["symbol"]) for path in namespace.glob("*.parquet")],
        ignore_index=True,
    )
    returned_symbols = set(pilot_bars["symbol"].astype(str))
    per_decile_rows = (
        pilot_bars["symbol"].map(all_deciles).value_counts().sort_index()
    )
    per_decile_returned_symbols = (
        pilot_bars.assign(decile=pilot_bars["symbol"].map(all_deciles))
        .groupby("decile")["symbol"]
        .nunique()
    )
    report = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "source_namespace": SIP_FIVE_MINUTE_NAMESPACE,
        "read_only_market_data": True,
        "execution_capability": "FORBIDDEN",
        "pilot_root": str(args.root.resolve()),
        "production_root": str(args.production_root.resolve()),
        "pilot_session": args.session.isoformat(),
        "sample_symbols": len(sample),
        "sample_symbols_sha256": sample_hash,
        "pilot_partition_set_sha256": partition_set_hash,
        "sample_liquidity_min": float(selected_scores.min()),
        "sample_liquidity_max": float(selected_scores.max()),
        "sample_decile_counts": {
            str(int(decile)): int(count) for decile, count in decile_counts.items()
        },
        "sample_rows_by_decile": {
            str(decile): int(per_decile_rows.get(decile, 0)) for decile in range(10)
        },
        "sample_returned_symbols_by_decile": {
            str(decile): int(per_decile_returned_symbols.get(decile, 0))
            for decile in range(10)
        },
        "sample_zero_row_symbols_by_decile": {
            str(decile): int(decile_counts.get(decile, 0))
            - int(per_decile_returned_symbols.get(decile, 0))
            for decile in range(10)
        },
        "sample_returned_symbols": len(returned_symbols),
        "sample_zero_row_symbols": len(sample) - len(returned_symbols),
        "candidate_zero_liquidity_scores": int(scores.eq(0).sum()),
        "daily_liquidity_source": _daily_source_identity(
            daily_source=args.daily_source, session=args.session
        ),
        "pilot_rows": int(validation["rows"]),
        "pilot_parquet_bytes": parquet_bytes,
        "pilot_manifest_bytes": manifest_bytes,
        "pilot_elapsed_seconds": elapsed_seconds,
        "last_validation_elapsed_seconds": validation_elapsed_seconds,
        "reused_existing_partitions": reused_existing_partitions,
        "provider_rejected_symbols": sum(
            len(cast(list[str], record["provider_rejected_symbols"]))
            for record in records
        ),
        "production_start": args.production_start.isoformat(),
        "production_end": args.production_end.isoformat(),
        "candidate_symbols": len(symbols),
        "expected_sessions": len(sessions),
        "expected_symbol_sessions": expected_symbol_sessions,
        "production_batch_size": args.production_batch_size,
        "capacity": capacity,
        "created_at": datetime.now().astimezone().isoformat(),
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, sort_keys=True), flush=True)
    if not capacity["safe_to_launch"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
