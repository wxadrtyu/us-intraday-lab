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

API_KEY_VARIABLE = "ALPACA_PAPER_API_KEY"
SECRET_KEY_VARIABLE = "ALPACA_PAPER_SECRET_KEY"
_REQUIRED_COLUMNS = ("symbol", "timestamp", "open", "high", "low", "close", "volume")
_OPTIONAL_COLUMNS = ("trade_count", "vwap")
_OUTPUT_COLUMNS = (*_REQUIRED_COLUMNS, *_OPTIONAL_COLUMNS, "asof", "provider", "feed")
_INVALID_SYMBOL_RESPONSE = re.compile(r"invalid symbol:\s*([^\"}]+)", re.IGNORECASE)
SIP_DAILY_NAMESPACE = "alpaca_sip_1day_v1"


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
    """Publish deterministic year/batch SIP shards and safely resume them."""
    if start > end:
        raise ValueError("daily acquisition start must not exceed end")
    if not symbols or len(symbols) != len(set(symbols)) or tuple(sorted(symbols)) != symbols:
        raise ValueError("symbols must be non-empty, unique, and sorted")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")

    output_root = root.resolve() / "data" / "staging" / SIP_DAILY_NAMESPACE
    output_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for year in range(start.year, end.year + 1):
        period_start = max(start, date(year, 1, 1))
        period_end = min(end, date(year, 12, 31))
        for offset in range(0, len(symbols), batch_size):
            batch = symbols[offset : offset + batch_size]
            identity = hashlib.sha256(",".join(batch).encode()).hexdigest()[:16]
            stem = f"{year}-batch-{offset // batch_size:04d}-{identity}"
            parquet = output_root / f"{stem}.parquet"
            manifest_path = output_root / f"{stem}.json"
            if parquet.is_file() and manifest_path.is_file():
                record = json.loads(manifest_path.read_text("utf-8"))
                if record["content_sha256"] != _sha256_file(parquet):
                    raise ValueError(f"SIP daily shard hash mismatch: {parquet}")
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

            temporary = parquet.with_suffix(".tmp.parquet")
            frame.to_parquet(temporary, index=False, compression="zstd")
            temporary.replace(parquet)
            record = {
                "schema_version": "1.0.0",
                "source_namespace": SIP_DAILY_NAMESPACE,
                "request_end_semantics": "exclusive_end_plus_one_day",
                "provider": "alpaca",
                "feed": "sip",
                "bar_size": "1day",
                "adjustment": "split",
                "year": year,
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
                "asof": period_end.isoformat(),
                "symbols": list(batch),
                "provider_rejected_symbols": sorted(rejected),
                "row_count": len(frame),
                "content_sha256": _sha256_file(parquet),
                "read_only_market_data": True,
            }
            temporary_manifest = manifest_path.with_suffix(".tmp")
            temporary_manifest.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            temporary_manifest.replace(manifest_path)
            records.append(record)
    return records
