"""Read-only US-equity master and coarse daily acquisition.

The asset directory is fetched through one allow-listed GET endpoint without
constructing Alpaca's trading client. Bars use only the historical data client.
No account, position, order, submit, or cancel capability exists here.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from datetime import time as datetime_time
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.request import Request, urlopen

import pandas as pd

from us_intraday_lab.data.alpaca_iex_acquisition import (
    API_KEY_VARIABLE,
    SECRET_KEY_VARIABLE,
)

ASSET_ENDPOINT = "https://paper-api.alpaca.markets/v2/assets?asset_class=us_equity"
PRIMARY_EXCHANGES = frozenset({"AMEX", "ARCA", "BATS", "NASDAQ", "NYSE"})
QUERYABLE_SYMBOL = re.compile(r"[A-Z][A-Z0-9.\-]{0,14}")
INVALID_SYMBOL_RESPONSE = re.compile(r"invalid symbol:\s*([^\"}]+)", re.IGNORECASE)
ASSET_COLUMNS = (
    "id",
    "class",
    "exchange",
    "symbol",
    "name",
    "status",
    "tradable",
    "marginable",
    "fractionable",
    "attributes",
)


class HistoricalBarsClient(Protocol):
    def get_stock_bars(self, request: object) -> Any: ...


JsonGetter = Callable[[str, Mapping[str, str]], object]


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _default_json_get(url: str, headers: Mapping[str, str]) -> object:
    request = Request(url, method="GET", headers=dict(headers))
    with urlopen(request, timeout=60) as response:
        return json.load(response)


def fetch_asset_catalog(
    *,
    environ: Mapping[str, str] | None = None,
    json_get: JsonGetter = _default_json_get,
) -> list[dict[str, object]]:
    values = os.environ if environ is None else environ
    api_key = values.get(API_KEY_VARIABLE, "")
    secret_key = values.get(SECRET_KEY_VARIABLE, "")
    if not api_key or not secret_key:
        raise RuntimeError("ALPACA_ASSET_CATALOG_CREDENTIAL_MISSING")
    payload = json_get(
        ASSET_ENDPOINT,
        {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key},
    )
    if not isinstance(payload, list):
        raise TypeError("Alpaca asset catalog response must be a list")
    return [cast(dict[str, object], item) for item in payload]


def normalize_asset_catalog(records: Sequence[Mapping[str, object]]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for record in records:
        row = {column: record.get(column) for column in ASSET_COLUMNS}
        row["symbol"] = str(row["symbol"] or "").strip().upper()
        row["exchange"] = str(row["exchange"] or "").strip().upper()
        row["status"] = str(row["status"] or "").strip().lower()
        row["attributes"] = _canonical_json(row["attributes"] or [])
        rows.append(row)
    frame = pd.DataFrame(rows, columns=ASSET_COLUMNS)
    if frame.empty or frame["id"].isna().any() or frame["symbol"].eq("").any():
        raise ValueError("Alpaca asset catalog contains missing identity fields")
    if frame["id"].duplicated().any():
        raise ValueError("Alpaca asset catalog contains duplicate asset IDs")
    return frame.sort_values(["symbol", "id"], kind="stable", ignore_index=True)


def publish_asset_catalog(
    frame: pd.DataFrame, *, root: Path, retrieved_at: datetime | None = None
) -> dict[str, object]:
    observed = datetime.now(UTC) if retrieved_at is None else retrieved_at.astimezone(UTC)
    canonical = root.resolve() / "data" / "catalog" / "us_equity_assets"
    canonical.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".assets-", dir=canonical))
    data_path = temporary / "assets.parquet"
    frame.to_parquet(data_path, index=False, compression="zstd")
    content_hash = _sha256_file(data_path)
    dataset_id = f"alpaca-us-equity-assets-{content_hash[:24]}"
    manifest = {
        "schema_version": "1.0.0",
        "dataset_id": dataset_id,
        "provider": "alpaca",
        "endpoint": ASSET_ENDPOINT,
        "retrieved_at": observed.isoformat(),
        "row_count": len(frame),
        "active_count": int(frame["status"].eq("active").sum()),
        "inactive_count": int(frame["status"].eq("inactive").sum()),
        "primary_exchange_count": int(frame["exchange"].isin(PRIMARY_EXCHANGES).sum()),
        "content_sha256": content_hash,
        "read_only": True,
    }
    (temporary / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", "utf-8"
    )
    final = canonical / dataset_id
    if final.exists():
        if _sha256_file(final / "assets.parquet") != content_hash:
            raise ValueError("immutable asset catalog collision")
        for child in temporary.iterdir():
            child.unlink()
        temporary.rmdir()
    else:
        temporary.rename(final)
    return manifest


def primary_exchange_symbols(frame: pd.DataFrame) -> tuple[str, ...]:
    retained = frame.loc[frame["exchange"].isin(PRIMARY_EXCHANGES), "symbol"]
    return tuple(
        sorted(symbol for symbol in set(retained.astype(str)) if QUERYABLE_SYMBOL.fullmatch(symbol))
    )


def unqueryable_primary_symbols(frame: pd.DataFrame) -> tuple[str, ...]:
    retained = frame.loc[frame["exchange"].isin(PRIMARY_EXCHANGES), "symbol"]
    return tuple(
        sorted(
            symbol for symbol in set(retained.astype(str)) if not QUERYABLE_SYMBOL.fullmatch(symbol)
        )
    )


class ReadOnlyDailyBarDownloader:
    def __init__(self, client: HistoricalBarsClient) -> None:
        self._client = client

    @classmethod
    def from_environment(cls) -> ReadOnlyDailyBarDownloader:
        from alpaca.data.historical import StockHistoricalDataClient

        api_key = os.environ.get(API_KEY_VARIABLE, "")
        secret_key = os.environ.get(SECRET_KEY_VARIABLE, "")
        if not api_key or not secret_key:
            raise RuntimeError("ALPACA_DAILY_CREDENTIAL_MISSING")
        return cls(StockHistoricalDataClient(api_key=api_key, secret_key=secret_key))

    def fetch(
        self, *, symbols: tuple[str, ...], start: date, end: date, asof: date
    ) -> pd.DataFrame:
        from alpaca.data.enums import Adjustment, DataFeed
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame

        request = StockBarsRequest(
            symbol_or_symbols=list(symbols),
            timeframe=TimeFrame.Day,
            start=datetime.combine(start, datetime_time(), UTC),
            end=datetime.combine(end, datetime_time(), UTC),
            adjustment=Adjustment.SPLIT,
            feed=DataFeed.IEX,
            asof=asof.isoformat(),
        )
        response = self._client.get_stock_bars(request)
        source = response.df.reset_index()
        if source.empty:
            return source
        source["symbol"] = source["symbol"].astype("string").str.upper()
        source["timestamp"] = pd.to_datetime(source["timestamp"], utc=True)
        source["asof"] = asof
        source["provider"] = "alpaca"
        source["feed"] = "iex"
        return source.sort_values(["symbol", "timestamp"], kind="stable", ignore_index=True)


def acquire_daily_shards(
    *,
    root: Path,
    downloader: ReadOnlyDailyBarDownloader,
    symbols: tuple[str, ...],
    start: date,
    end: date,
    batch_size: int = 100,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, object]]:
    output_root = root.resolve() / "data" / "staging" / "alpaca_iex_1day"
    output_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    if start > end:
        raise ValueError("daily acquisition start must not exceed end")
    for year in range(start.year, end.year + 1):
        period_start = max(start, date(year, 1, 1))
        period_end = min(end, date(year, 12, 31))
        asof = period_end
        for offset in range(0, len(symbols), batch_size):
            batch = symbols[offset : offset + batch_size]
            identity = hashlib.sha256(",".join(batch).encode()).hexdigest()[:16]
            stem = f"{year}-batch-{offset // batch_size:04d}-{identity}"
            parquet = output_root / f"{stem}.parquet"
            manifest_path = output_root / f"{stem}.json"
            if parquet.is_file() and manifest_path.is_file():
                record = cast(dict[str, object], json.loads(manifest_path.read_text("utf-8")))
                if record["content_sha256"] != _sha256_file(parquet):
                    raise ValueError(f"daily shard hash mismatch: {parquet}")
                records.append(record)
                continue
            if parquet.exists() or manifest_path.exists():
                raise ValueError(f"partial daily shard requires audit: {stem}")
            last_error: Exception | None = None
            rejected: list[str] = []
            remaining = list(batch)
            attempt = 0
            while remaining:
                try:
                    frame = downloader.fetch(
                        symbols=tuple(remaining),
                        start=period_start,
                        end=period_end,
                        asof=asof,
                    )
                    break
                except Exception as error:  # bounded provider retry
                    last_error = error
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
                if last_error is None:
                    raise AssertionError("empty symbol batch")
                frame = pd.DataFrame()
            temporary = parquet.with_suffix(".tmp.parquet")
            frame.to_parquet(temporary, index=False, compression="zstd")
            temporary.replace(parquet)
            record = {
                "schema_version": "1.0.0",
                "provider": "alpaca",
                "feed": "iex",
                "bar_size": "1day",
                "adjustment": "split",
                "year": year,
                "start": period_start.isoformat(),
                "end": period_end.isoformat(),
                "asof": asof.isoformat(),
                "symbols": list(batch),
                "provider_rejected_symbols": sorted(rejected),
                "row_count": len(frame),
                "content_sha256": _sha256_file(parquet),
            }
            temporary_manifest = manifest_path.with_suffix(".tmp")
            temporary_manifest.write_text(
                json.dumps(record, indent=2, sort_keys=True) + "\n", "utf-8"
            )
            temporary_manifest.replace(manifest_path)
            records.append(record)
    return records
