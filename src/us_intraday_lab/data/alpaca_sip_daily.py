"""Read-only Alpaca SIP daily-bar access.

Only Alpaca's historical market-data client is imported.  This module has no
account, broker, position, order, submit, or cancel capability.
"""

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

import pandas as pd
import pyarrow.parquet as pq

API_KEY_VARIABLE = "ALPACA_PAPER_API_KEY"
SECRET_KEY_VARIABLE = "ALPACA_PAPER_SECRET_KEY"
_REQUIRED_COLUMNS = ("symbol", "timestamp", "open", "high", "low", "close", "volume")
_OPTIONAL_COLUMNS = ("trade_count", "vwap")
_OUTPUT_COLUMNS = (*_REQUIRED_COLUMNS, *_OPTIONAL_COLUMNS, "asof", "provider", "feed")
_INVALID_SYMBOL_RESPONSE = re.compile(r"invalid symbol:\s*([^\"}]+)", re.IGNORECASE)
SIP_DAILY_NAMESPACE = "alpaca_sip_1day_v2"


class HistoricalBarsClient(Protocol):
    def get_stock_bars(self, request: object) -> Any: ...


HistoricalClientFactory = Callable[[str, str], HistoricalBarsClient]


def _client_factory(api_key: str, secret_key: str) -> HistoricalBarsClient:
    from alpaca.data.historical import StockHistoricalDataClient

    return cast(
        HistoricalBarsClient,
        StockHistoricalDataClient(api_key=api_key, secret_key=secret_key),
    )


class ReadOnlyAlpacaSipDailyDownloader:
    """Fetch split-adjusted consolidated daily bars without trading access."""

    def __init__(self, client: HistoricalBarsClient) -> None:
        self._client = client

    @classmethod
    def from_environment(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        client_factory: HistoricalClientFactory = _client_factory,
    ) -> ReadOnlyAlpacaSipDailyDownloader:
        values = os.environ if environ is None else environ
        api_key = values.get(API_KEY_VARIABLE, "")
        secret_key = values.get(SECRET_KEY_VARIABLE, "")
        if not api_key or not secret_key:
            raise RuntimeError(
                "ALPACA_SIP_DAILY_CREDENTIAL_MISSING: set "
                f"{API_KEY_VARIABLE} and {SECRET_KEY_VARIABLE}"
            )
        return cls(client_factory(api_key, secret_key))

    def fetch(
        self,
        *,
        symbols: tuple[str, ...],
        start: date,
        end: date,
        asof: date,
    ) -> pd.DataFrame:
        from alpaca.data.enums import Adjustment, DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        if not symbols or len(symbols) != len(set(symbols)) or tuple(sorted(symbols)) != symbols:
            raise ValueError("symbols must be non-empty, unique, and sorted")
        if start > end:
            raise ValueError("start must not exceed end")

        request = StockBarsRequest(
            symbol_or_symbols=list(symbols),
            timeframe=TimeFrame.Day,
            start=datetime.combine(start, time(), UTC),
            end=datetime.combine(end + timedelta(days=1), time(), UTC),
            adjustment=Adjustment.SPLIT,
            feed=DataFeed.SIP,
            asof=asof.isoformat(),
        )
        response = self._client.get_stock_bars(request)
        return _normalize_daily_bars(response.df.reset_index(), asof=asof)


def _normalize_daily_bars(frame: pd.DataFrame, *, asof: date) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=_OUTPUT_COLUMNS)
    missing = sorted(set(_REQUIRED_COLUMNS).difference(frame.columns))
    if missing:
        raise ValueError(f"Alpaca SIP daily response missing columns: {missing}")

    result = frame.loc[:, [column for column in (*_REQUIRED_COLUMNS, *_OPTIONAL_COLUMNS) if column in frame]].copy()
    result["symbol"] = result["symbol"].astype(str).str.upper()
    result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True)
    for column in ("open", "high", "low", "close", "volume", *_OPTIONAL_COLUMNS):
        if column not in result:
            result[column] = pd.NA
        result[column] = pd.to_numeric(result[column], errors="coerce")
    result["asof"] = asof
    result["provider"] = "alpaca"
    result["feed"] = "sip"
    return result.loc[:, _OUTPUT_COLUMNS].sort_values(["timestamp", "symbol"]).reset_index(drop=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _month_ranges(start: date, end: date) -> tuple[tuple[date, date], ...]:
    ranges: list[tuple[date, date]] = []
    cursor = start
    while cursor <= end:
        next_month = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
        period_end = min(end, next_month - timedelta(days=1))
        ranges.append((cursor, period_end))
        cursor = period_end + timedelta(days=1)
    return tuple(ranges)


def _request_identity(
    *, symbols: tuple[str, ...], start: date, end: date, asof: date
) -> dict[str, object]:
    return {
        "provider": "alpaca",
        "feed": "sip",
        "bar_size": "1day",
        "adjustment": "split",
        "start": start.isoformat(),
        "end": end.isoformat(),
        "asof": asof.isoformat(),
        "symbols": list(symbols),
    }


def _identity_hash(identity: dict[str, object]) -> str:
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _partition_stem(
    *, period_start: date, offset: int, batch_size: int, identity_hash: str
) -> str:
    return (
        f"{period_start:%Y-%m}-batch-{offset // batch_size:04d}-"
        f"{identity_hash[:16]}"
    )


def _quality(
    frame: pd.DataFrame, *, requested: tuple[str, ...], start: date, end: date
) -> dict[str, object]:
    if frame.empty:
        return {
            "returned_rows": 0,
            "returned_symbols": 0,
            "duplicate_symbol_sessions": 0,
            "missing_required_values": 0,
        }
    returned = set(frame["symbol"].astype(str).str.upper())
    unexpected = sorted(returned.difference(requested))
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    outside = frame.loc[(timestamps.dt.date < start) | (timestamps.dt.date > end)]
    duplicates = int(frame.duplicated(["symbol", "timestamp"]).sum())
    missing = int(frame.loc[:, _REQUIRED_COLUMNS].isna().any(axis=1).sum())
    if unexpected or not outside.empty or duplicates or missing:
        raise ValueError(
            "SIP daily quality failure: "
            f"unexpected_symbols={unexpected}, outside_bounds={len(outside)}, "
            f"duplicates={duplicates}, missing_required={missing}"
        )
    return {
        "returned_rows": len(frame),
        "returned_symbols": len(returned),
        "duplicate_symbol_sessions": duplicates,
        "missing_required_values": missing,
    }


def acquire_sip_daily_shards(
    *,
    root: Path,
    downloader: ReadOnlyAlpacaSipDailyDownloader,
    symbols: tuple[str, ...],
    start: date,
    end: date,
    batch_size: int = 100,
    sleep: Callable[[float], None] = time_module.sleep,
) -> list[dict[str, object]]:
    """Publish deterministic month/batch SIP shards and safely resume them."""
    if start > end:
        raise ValueError("daily acquisition start must not exceed end")
    if not symbols or len(symbols) != len(set(symbols)) or tuple(sorted(symbols)) != symbols:
        raise ValueError("symbols must be non-empty, unique, and sorted")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    output_root = root.resolve() / "data" / "staging" / SIP_DAILY_NAMESPACE
    output_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for period_start, period_end in _month_ranges(start, end):
        for offset in range(0, len(symbols), batch_size):
            batch = symbols[offset : offset + batch_size]
            request_identity = _request_identity(
                symbols=batch, start=period_start, end=period_end, asof=period_end
            )
            identity_hash = _identity_hash(request_identity)
            stem = _partition_stem(
                period_start=period_start,
                offset=offset,
                batch_size=batch_size,
                identity_hash=identity_hash,
            )
            parquet = output_root / f"{stem}.parquet"
            manifest_path = output_root / f"{stem}.json"
            if parquet.is_file() and manifest_path.is_file():
                record = json.loads(manifest_path.read_text("utf-8"))
                if record["content_sha256"] != _sha256_file(parquet):
                    raise ValueError(f"SIP daily shard hash mismatch: {parquet}")
                if record.get("request_identity_sha256") != identity_hash:
                    raise ValueError(f"SIP daily request identity mismatch: {stem}")
                if record.get("request") != request_identity:
                    raise ValueError(f"SIP daily request manifest mismatch: {stem}")
                records.append(record)
                continue
            if parquet.exists() or manifest_path.exists():
                raise ValueError(f"partial SIP daily shard requires audit: {stem}")

            rejected: list[str] = []
            remaining = list(batch)
            attempt = 0
            while remaining:
                try:
                    frame = downloader.fetch(
                        symbols=tuple(remaining),
                        start=period_start,
                        end=period_end,
                        asof=period_end,
                    )
                    break
                except Exception as error:
                    invalid = _INVALID_SYMBOL_RESPONSE.search(str(error))
                    if invalid and invalid.group(1).strip().upper() in remaining:
                        bad_symbol = invalid.group(1).strip().upper()
                        remaining.remove(bad_symbol)
                        rejected.append(bad_symbol)
                        continue
                    if attempt >= 4:
                        raise
                    sleep(min(30.0, 2.0**attempt))
                    attempt += 1
            else:
                frame = pd.DataFrame(columns=_OUTPUT_COLUMNS)

            quality = _quality(
                frame, requested=tuple(remaining), start=period_start, end=period_end
            )
            retrieved_at = datetime.now(UTC).isoformat()
            temporary = parquet.with_suffix(".tmp.parquet")
            frame.to_parquet(temporary, index=False, compression="zstd")
            temporary.replace(parquet)
            record = {
                "schema_version": "2.0.0",
                "source_namespace": SIP_DAILY_NAMESPACE,
                "request_end_semantics": "exclusive_end_plus_one_day",
                "provider": "alpaca",
                "feed": "sip",
                "bar_size": "1day",
                "adjustment": "split",
                "year": period_start.year,
                "month": period_start.month,
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
                "asof": period_end.isoformat(),
                "symbols": list(batch),
                "provider_rejected_symbols": sorted(rejected),
                "row_count": len(frame),
                "content_sha256": _sha256_file(parquet),
                "read_only_market_data": True,
                "request": request_identity,
                "request_identity_sha256": identity_hash,
                "retrieved_at": retrieved_at,
                "quality": quality,
            }
            temporary_manifest = manifest_path.with_suffix(".tmp")
            temporary_manifest.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            temporary_manifest.replace(manifest_path)
            records.append(record)
    return records


def validate_sip_daily_source(
    *,
    root: Path,
    symbols: tuple[str, ...] | None = None,
    start: date | None = None,
    end: date | None = None,
    batch_size: int | None = None,
) -> dict[str, int]:
    """Validate every immutable v2 partition before downstream consumption."""
    source = root.resolve() / "data" / "staging" / SIP_DAILY_NAMESPACE
    parquet_by_stem = {path.stem: path for path in source.glob("*.parquet")}
    manifest_by_stem = {path.stem: path for path in source.glob("*.json")}
    partials = tuple(source.glob("*.tmp")) + tuple(source.glob("*.tmp.parquet"))
    if not parquet_by_stem and not manifest_by_stem:
        raise ValueError("SIP daily source is empty")
    if parquet_by_stem.keys() != manifest_by_stem.keys() or partials:
        raise ValueError("SIP daily partition pairing failure")
    grid_args = (symbols, start, end, batch_size)
    if any(value is not None for value in grid_args) and not all(
        value is not None for value in grid_args
    ):
        raise ValueError("complete expected grid arguments are required")
    if symbols is not None and start is not None and end is not None and batch_size is not None:
        expected: set[str] = set()
        for period_start, period_end in _month_ranges(start, end):
            for offset in range(0, len(symbols), batch_size):
                batch = symbols[offset : offset + batch_size]
                identity = _request_identity(
                    symbols=batch,
                    start=period_start,
                    end=period_end,
                    asof=period_end,
                )
                expected.add(
                    _partition_stem(
                        period_start=period_start,
                        offset=offset,
                        batch_size=batch_size,
                        identity_hash=_identity_hash(identity),
                    )
                )
        if parquet_by_stem.keys() != expected:
            raise ValueError("SIP daily expected acquisition grid mismatch")

    total_rows = 0
    for stem, parquet in sorted(parquet_by_stem.items()):
        record = json.loads(manifest_by_stem[stem].read_text("utf-8"))
        request = record.get("request")
        if not isinstance(request, dict):
            raise TypeError(f"SIP daily request manifest missing: {stem}")
        request_hash = _identity_hash(request)
        request_start = str(request.get("start", ""))
        if (
            record.get("source_namespace") != SIP_DAILY_NAMESPACE
            or record.get("provider") != "alpaca"
            or record.get("feed") != "sip"
            or record.get("bar_size") != "1day"
            or record.get("adjustment") != "split"
            or request.get("feed") != "sip"
            or request.get("provider") != record.get("provider")
            or request.get("bar_size") != record.get("bar_size")
            or request.get("adjustment") != record.get("adjustment")
            or request.get("start") != record.get("start")
            or request.get("end") != record.get("end")
            or request.get("asof") != record.get("asof")
            or request.get("symbols") != record.get("symbols")
            or record.get("request_identity_sha256") != request_hash
            or not stem.startswith(f"{request_start[:7]}-batch-")
            or not stem.endswith(request_hash[:16])
            or record.get("content_sha256") != _sha256_file(parquet)
        ):
            raise ValueError(f"SIP daily provenance failure: {stem}")
        rows = int(pq.ParquetFile(parquet).metadata.num_rows)
        if rows != int(record.get("row_count", -1)):
            raise ValueError(f"SIP daily row-count failure: {stem}")
        if rows:
            columns = [*_REQUIRED_COLUMNS, "asof", "provider", "feed"]
            frame = pq.read_table(parquet, columns=columns).to_pandas()
            requested = set(request["symbols"])
            timestamps = pd.to_datetime(frame["timestamp"], utc=True)
            if (
                set(frame["symbol"].astype(str).str.upper()).difference(requested)
                or set(frame["provider"].astype(str)) != {"alpaca"}
                or set(frame["feed"].astype(str)) != {"sip"}
                or set(frame["asof"].astype(str)) != {str(request["asof"])}
                or timestamps.dt.date.min() < date.fromisoformat(str(request["start"]))
                or timestamps.dt.date.max() > date.fromisoformat(str(request["end"]))
                or frame.duplicated(["symbol", "timestamp"]).any()
                or frame.loc[:, _REQUIRED_COLUMNS].isna().any(axis=None)
            ):
                raise ValueError(f"SIP daily parquet provenance failure: {stem}")
        total_rows += rows
    return {"partitions": len(parquet_by_stem), "rows": total_rows}
