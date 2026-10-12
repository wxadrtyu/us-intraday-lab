"""Read-only Alpaca SIP one-minute source with deterministic request identities."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time as time_module
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from us_intraday_lab.data.alpaca_sip_five_minute import _regular_session_mask
from us_intraday_lab.data.alpaca_sip_five_minute import (
    load_frozen_candidate_symbols as _load_frozen_candidate_symbols,
)

API_KEY_VARIABLE = "ALPACA_PAPER_API_KEY"
SECRET_KEY_VARIABLE = "ALPACA_PAPER_SECRET_KEY"
SIP_ONE_MINUTE_NAMESPACE = "alpaca_sip_1min_v1"
_REQUIRED = ("symbol", "timestamp", "open", "high", "low", "close", "volume")
_OPTIONAL = ("trade_count", "vwap")
_OUTPUT = (*_REQUIRED, *_OPTIONAL, "asof", "provider", "feed")
_INVALID_SYMBOL = re.compile(r'invalid symbol:\s*([^"}]+)', re.IGNORECASE)


def load_frozen_candidate_symbols(*, assets_path: Path, protocol_path: Path) -> tuple[str, ...]:
    return _load_frozen_candidate_symbols(assets_path=assets_path, protocol_path=protocol_path)


class HistoricalBarsClient(Protocol):
    def get_stock_bars(self, request: object) -> Any: ...


class ReadOnlyAlpacaSipOneMinuteDownloader:
    """Read historical bars without constructing a trading client."""

    def __init__(self, client: HistoricalBarsClient) -> None:
        self._client = client

    @classmethod
    def from_environment(
        cls, *, environ: Mapping[str, str] | None = None
    ) -> ReadOnlyAlpacaSipOneMinuteDownloader:
        from alpaca.data.historical import StockHistoricalDataClient

        values = os.environ if environ is None else environ
        api_key = values.get(API_KEY_VARIABLE, "")
        secret_key = values.get(SECRET_KEY_VARIABLE, "")
        if not api_key or not secret_key:
            raise RuntimeError(
                "ALPACA_SIP_ONE_MINUTE_CREDENTIAL_MISSING: set "
                f"{API_KEY_VARIABLE} and {SECRET_KEY_VARIABLE}"
            )
        return cls(StockHistoricalDataClient(api_key=api_key, secret_key=secret_key))

    def fetch(
        self, *, symbols: tuple[str, ...], start: date, end: date, asof: date
    ) -> pd.DataFrame:
        from alpaca.data.enums import Adjustment, DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        _validate_symbols(symbols)
        if start > end:
            raise ValueError("start must not exceed end")
        request = StockBarsRequest(
            symbol_or_symbols=list(symbols),
            timeframe=TimeFrame(1, TimeFrameUnit.Minute),
            start=datetime.combine(start, time(), UTC),
            end=datetime.combine(end + timedelta(days=1), time(), UTC),
            adjustment=Adjustment.SPLIT,
            feed=DataFeed.SIP,
            asof=asof.isoformat(),
        )
        return normalize_one_minute_bars(
            self._client.get_stock_bars(request).df.reset_index(), asof=asof
        )


def normalize_one_minute_bars(frame: pd.DataFrame, *, asof: date) -> pd.DataFrame:
    """Preserve source-row accounting while selecting XNYS regular-session bars."""
    if frame.empty:
        empty = pd.DataFrame(columns=_OUTPUT)
        empty.attrs["provider_source_rows"] = 0
        empty.attrs["excluded_out_of_session_rows"] = 0
        return empty
    missing = sorted(set(_REQUIRED).difference(frame.columns))
    if missing:
        raise ValueError(f"Alpaca SIP one-minute response missing columns: {missing}")
    rows = len(frame)
    result = frame.loc[:, [column for column in (*_REQUIRED, *_OPTIONAL) if column in frame]].copy()
    result["symbol"] = result["symbol"].astype(str).str.upper()
    result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True, errors="raise")
    for column in ("open", "high", "low", "close", "volume", *_OPTIONAL):
        if column not in result:
            result[column] = pd.NA
        result[column] = pd.to_numeric(result[column], errors="raise")
    result["asof"] = asof
    result["provider"] = "alpaca"
    result["feed"] = "sip"
    result = result.loc[_regular_session_mask(result["timestamp"]), _OUTPUT]
    result = result.sort_values(["timestamp", "symbol"], kind="stable").reset_index(drop=True)
    result.attrs["provider_source_rows"] = rows
    result.attrs["excluded_out_of_session_rows"] = rows - len(result)
    return result


def quality_report(
    frame: pd.DataFrame,
    *,
    requested: tuple[str, ...],
    start: date,
    end: date,
    asof: date,
) -> dict[str, int]:
    """Reject malformed source bars before they can enter a strategy panel."""
    if frame.empty:
        return {"returned_rows": 0, "returned_symbols": 0}
    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    unexpected = sorted(set(frame["symbol"].astype(str)).difference(requested))
    outside = (timestamps.dt.date < start) | (timestamps.dt.date > end)
    outside_session = ~_regular_session_mask(timestamps)
    duplicates = int(frame.duplicated(["symbol", "timestamp"]).sum())
    missing = int(frame.loc[:, _REQUIRED].isna().any(axis=1).sum())
    prices = frame[["open", "high", "low", "close"]]
    invalid_ohlc = (
        prices.le(0).any(axis=1)
        | frame["high"].lt(prices[["open", "low", "close"]].max(axis=1))
        | frame["low"].gt(prices[["open", "high", "close"]].min(axis=1))
        | frame["volume"].lt(0)
    )
    off_grid = timestamps.dt.second.ne(0) | timestamps.dt.microsecond.ne(0)
    nonfinite = sum(
        int((~np.isfinite(frame[column].dropna().astype(float))).sum())
        for column in ("open", "high", "low", "close", "volume", *_OPTIONAL)
    )
    bad_trade_count = int(frame["trade_count"].dropna().lt(0).sum())
    bad_vwap = int(frame["vwap"].dropna().le(0).sum())
    source_bad = (
        set(frame["provider"].astype(str)) != {"alpaca"}
        or set(frame["feed"].astype(str)) != {"sip"}
        or set(frame["asof"].astype(str)) != {asof.isoformat()}
    )
    if (
        unexpected
        or outside.any()
        or outside_session.any()
        or duplicates
        or missing
        or invalid_ohlc.any()
        or off_grid.any()
        or nonfinite
        or bad_trade_count
        or bad_vwap
        or source_bad
    ):
        raise ValueError(
            "SIP one-minute quality failure: "
            f"unexpected_symbols={unexpected}, outside_bounds={int(outside.sum())}, "
            f"outside_session={int(outside_session.sum())}, duplicates={duplicates}, "
            f"missing_required={missing}, invalid_ohlc={int(invalid_ohlc.sum())}, "
            f"off_grid={int(off_grid.sum())}, nonfinite={nonfinite}, "
            f"invalid_trade_count={bad_trade_count}, invalid_vwap={bad_vwap}, "
            f"source_bad={source_bad}"
        )
    return {"returned_rows": len(frame), "returned_symbols": frame["symbol"].nunique()}


def _validate_symbols(symbols: tuple[str, ...]) -> None:
    if not symbols or symbols != tuple(sorted(set(symbols))):
        raise ValueError("symbols must be nonempty, unique, and sorted")


def _month_ranges(start: date, end: date) -> tuple[tuple[date, date], ...]:
    periods: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        next_month = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        period_end = min(end, next_month - timedelta(days=1))
        periods.append((cursor, period_end))
        cursor = period_end + timedelta(days=1)
    return tuple(periods)


def partition_specs(
    *, symbols: tuple[str, ...], start: date, end: date, batch_size: int
) -> tuple[dict[str, object], ...]:
    _validate_symbols(symbols)
    if start > end or batch_size < 1:
        raise ValueError("invalid acquisition bounds or batch size")
    specs: list[dict[str, object]] = []
    for period_start, period_end in _month_ranges(start, end):
        for offset in range(0, len(symbols), batch_size):
            batch = symbols[offset : offset + batch_size]
            request: dict[str, object] = {
                "provider": "alpaca",
                "feed": "sip",
                "bar_size": "1min",
                "adjustment": "split",
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
                "asof": period_end.isoformat(),
                "batch_size": batch_size,
                "symbols": list(batch),
            }
            digest = hashlib.sha256(
                json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            specs.append(
                {
                    "global_shard_index": len(specs),
                    "period_start": period_start,
                    "period_end": period_end,
                    "batch": batch,
                    "request": request,
                    "request_identity_sha256": digest,
                    "stem": f"{period_start:%Y-%m}-batch-{offset // batch_size:04d}-{digest[:16]}",
                }
            )
    return tuple(specs)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contract(
    *, symbols: tuple[str, ...], start: date, end: date, batch_size: int
) -> dict[str, object]:
    return {
        "schema_version": "1.0.0",
        "source_namespace": SIP_ONE_MINUTE_NAMESPACE,
        "provider": "alpaca",
        "feed": "sip",
        "bar_size": "1min",
        "adjustment": "split",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "batch_size": batch_size,
        "candidate_symbol_count": len(symbols),
        "candidate_symbols_sha256": hashlib.sha256("\n".join(symbols).encode()).hexdigest(),
        "total_shards": len(
            partition_specs(symbols=symbols, start=start, end=end, batch_size=batch_size)
        ),
        "read_only_market_data": True,
    }


def _ensure_contract(
    source: Path, *, symbols: tuple[str, ...], start: date, end: date, batch_size: int
) -> None:
    expected = _contract(symbols=symbols, start=start, end=end, batch_size=batch_size)
    path = source / "acquisition_contract.json"
    if not path.exists() and any(source.iterdir()):
        raise ValueError("SIP one-minute acquisition contract missing for populated namespace")
    try:
        with path.open("x", encoding="utf-8") as target:
            target.write(json.dumps(expected, indent=2, sort_keys=True) + "\n")
    except FileExistsError:
        pass
    if json.loads(path.read_text("utf-8")) != expected:
        raise ValueError("SIP one-minute acquisition contract mismatch")


def _validate_shard(parquet: Path, record: dict[str, object], spec: dict[str, object]) -> int:
    request = cast(dict[str, object], spec["request"])
    digest = hashlib.sha256(
        json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if record.get("request") != request or record.get("request_identity_sha256") != digest:
        raise ValueError(f"SIP one-minute request identity mismatch: {spec['stem']}")
    if (
        record.get("source_namespace") != SIP_ONE_MINUTE_NAMESPACE
        or record.get("provider") != "alpaca"
        or record.get("feed") != "sip"
        or record.get("bar_size") != "1min"
        or record.get("adjustment") != "split"
        or record.get("content_sha256") != _hash_file(parquet)
        or record.get("global_shard_index") != spec["global_shard_index"]
    ):
        raise ValueError(f"SIP one-minute provenance failure: {spec['stem']}")
    rows = pq.ParquetFile(parquet).metadata.num_rows
    if rows != record.get("row_count"):
        raise ValueError(f"SIP one-minute row-count failure: {spec['stem']}")
    source_rows = record.get("provider_source_rows")
    excluded = record.get("excluded_out_of_session_rows")
    if (
        not isinstance(source_rows, int)
        or not isinstance(excluded, int)
        or source_rows - excluded != rows
        or excluded < 0
    ):
        raise ValueError(f"SIP one-minute source-row accounting failure: {spec['stem']}")
    frame = pq.read_table(parquet).to_pandas()
    requested_symbols = tuple(cast(list[str], request["symbols"]))
    rejected = record.get("provider_rejected_symbols")
    if (
        not isinstance(rejected, list)
        or rejected != sorted(set(rejected))
        or not set(rejected).issubset(requested_symbols)
        or set(rejected).intersection(frame["symbol"].astype(str))
    ):
        raise ValueError(f"SIP one-minute rejection ledger failure: {spec['stem']}")
    observed = quality_report(
        frame,
        requested=tuple(symbol for symbol in requested_symbols if symbol not in rejected),
        start=date.fromisoformat(str(request["start"])),
        end=date.fromisoformat(str(request["end"])),
        asof=date.fromisoformat(str(request["asof"])),
    )
    if observed != record.get("quality"):
        raise ValueError(f"SIP one-minute quality-manifest mismatch: {spec['stem']}")
    return rows


def acquire_sip_one_minute_shards(
    *,
    root: Path,
    downloader: ReadOnlyAlpacaSipOneMinuteDownloader,
    symbols: tuple[str, ...],
    start: date,
    end: date,
    batch_size: int = 100,
    shard_start: int = 0,
    shard_stop: int | None = None,
    sleep: Callable[[float], None] = time_module.sleep,
) -> list[dict[str, object]]:
    """Acquire only an explicit finite slice; fail closed on any partial shard."""
    _validate_symbols(symbols)
    if (
        start > end
        or batch_size < 1
        or shard_start < 0
        or shard_stop is None
        or shard_stop <= shard_start
    ):
        raise ValueError("finite valid shard bounds required")
    specs = partition_specs(symbols=symbols, start=start, end=end, batch_size=batch_size)
    if shard_stop > len(specs):
        raise ValueError("shard_stop exceeds frozen grid")
    source = root.resolve() / "data" / "staging" / SIP_ONE_MINUTE_NAMESPACE
    source.mkdir(parents=True, exist_ok=True)
    _ensure_contract(source, symbols=symbols, start=start, end=end, batch_size=batch_size)
    records: list[dict[str, object]] = []
    for spec in specs[shard_start:shard_stop]:
        stem = str(spec["stem"])
        parquet = source / f"{stem}.parquet"
        manifest = source / f"{stem}.json"
        temporary_parquet = source / f"{stem}.tmp.parquet"
        temporary_manifest = source / f"{stem}.tmp"
        if temporary_parquet.exists() or temporary_manifest.exists():
            raise ValueError(f"temporary SIP one-minute shard requires audit: {stem}")
        if parquet.is_file() and manifest.is_file():
            record = cast(dict[str, object], json.loads(manifest.read_text("utf-8")))
            _validate_shard(parquet, record, spec)
            records.append(record)
            continue
        if parquet.exists() or manifest.exists():
            raise ValueError(f"partial SIP one-minute shard requires audit: {stem}")
        request = cast(dict[str, object], spec["request"])
        remaining = list(cast(tuple[str, ...], spec["batch"]))
        rejected: list[str] = []
        attempt = 0
        while remaining:
            try:
                frame = downloader.fetch(
                    symbols=tuple(remaining),
                    start=cast(date, spec["period_start"]),
                    end=cast(date, spec["period_end"]),
                    asof=cast(date, spec["period_end"]),
                )
                if frame.empty:
                    raise RuntimeError(
                        f"ALPACA_SIP_ONE_MINUTE_EMPTY_RESPONSE: {spec['request_identity_sha256']}"
                    )
                break
            except Exception as error:
                invalid = _INVALID_SYMBOL.search(str(error))
                if invalid and invalid.group(1).strip().upper() in remaining:
                    symbol = invalid.group(1).strip().upper()
                    remaining.remove(symbol)
                    rejected.append(symbol)
                    continue
                if attempt >= 4:
                    raise
                sleep(min(30.0, 2.0**attempt))
                attempt += 1
        else:
            frame = normalize_one_minute_bars(pd.DataFrame(), asof=cast(date, spec["period_end"]))
        quality = quality_report(
            frame,
            requested=tuple(remaining),
            start=cast(date, spec["period_start"]),
            end=cast(date, spec["period_end"]),
            asof=cast(date, spec["period_end"]),
        )
        source_rows = int(frame.attrs.get("provider_source_rows", len(frame)))
        excluded = int(frame.attrs.get("excluded_out_of_session_rows", 0))
        frame.to_parquet(temporary_parquet, index=False, compression="zstd")
        temporary_parquet.replace(parquet)
        record: dict[str, object] = {
            "schema_version": "1.0.0",
            "source_namespace": SIP_ONE_MINUTE_NAMESPACE,
            "provider": "alpaca",
            "feed": "sip",
            "bar_size": "1min",
            "adjustment": "split",
            "start": request["start"],
            "end": request["end"],
            "asof": request["asof"],
            "symbols": request["symbols"],
            "provider_rejected_symbols": sorted(rejected),
            "row_count": len(frame),
            "provider_source_rows": source_rows,
            "excluded_out_of_session_rows": excluded,
            "quality": quality,
            "read_only_market_data": True,
            "request": request,
            "request_identity_sha256": spec["request_identity_sha256"],
            "content_sha256": _hash_file(parquet),
            "retrieved_at": datetime.now(UTC).isoformat(),
            "global_shard_index": spec["global_shard_index"],
        }
        temporary_manifest.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        temporary_manifest.replace(manifest)
        records.append(record)
    return records


def validate_sip_one_minute_source(
    *, root: Path, symbols: tuple[str, ...], start: date, end: date, batch_size: int
) -> dict[str, int]:
    """Deeply verify every shard in the complete frozen grid."""
    _validate_symbols(symbols)
    source = root.resolve() / "data" / "staging" / SIP_ONE_MINUTE_NAMESPACE
    if not source.is_dir():
        raise ValueError("SIP one-minute source missing")
    _ensure_contract(source, symbols=symbols, start=start, end=end, batch_size=batch_size)
    specs = partition_specs(symbols=symbols, start=start, end=end, batch_size=batch_size)
    expected = {str(spec["stem"]): spec for spec in specs}
    parquets = {path.stem: path for path in source.glob("*.parquet")}
    manifests = {
        path.stem: path
        for path in source.glob("*.json")
        if path.name != "acquisition_contract.json"
    }
    if (
        any(source.glob("*.tmp"))
        or any(source.glob("*.tmp.parquet"))
        or parquets.keys() != expected.keys()
        or manifests.keys() != expected.keys()
    ):
        raise ValueError("SIP one-minute incomplete or partial acquisition grid")
    rows = 0
    for stem, spec in sorted(expected.items()):
        record = cast(dict[str, object], json.loads(manifests[stem].read_text("utf-8")))
        rows += _validate_shard(parquets[stem], record, spec)
    return {"partitions": len(expected), "rows": rows}
