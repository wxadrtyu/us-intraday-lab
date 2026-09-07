"""Read-only, batched historical quote-feature acquisition.

The acquisition unit is a decision timestamp crossed with every eligible symbol,
not an individual strategy or ticker.  Only Alpaca's historical market-data
client is imported; this module has no account, broker, order, submit, or cancel
capability.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

import exchange_calendars  # type: ignore[import-untyped]
import numpy as np
import pandas as pd

from us_intraday_lab.data.alpaca_iex_acquisition import (
    API_KEY_VARIABLE,
    BLIND_CUTOFF,
    SECRET_KEY_VARIABLE,
)

_XNYS = exchange_calendars.get_calendar("XNYS")
LOOKBACK_SECONDS = (1, 5, 30, 120)
QUOTE_COLUMNS = (
    "symbol",
    "timestamp",
    "bid_price",
    "bid_size",
    "bid_exchange",
    "ask_price",
    "ask_size",
    "ask_exchange",
    "conditions",
    "tape",
)


class HistoricalQuotesClient(Protocol):
    def get_stock_quotes(self, request: object) -> Any: ...


Sleep = Callable[[float], None]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decision_timestamp(session_date: date, bar_idx: int) -> datetime:
    """Return the exclusive information cutoff after a completed five-minute bar."""
    if bar_idx < 0 or bar_idx > 77:
        raise ValueError("bar_idx must be on the 78-bar XNYS five-minute grid")
    session = pd.Timestamp(session_date)
    market_open = cast(datetime, _XNYS.session_open(session).to_pydatetime()).astimezone(UTC)
    return market_open + timedelta(minutes=(bar_idx + 1) * 5)


class ReadOnlyAlpacaQuoteDownloader:
    def __init__(self, client: HistoricalQuotesClient, *, feed: str = "sip") -> None:
        if feed not in {"iex", "sip"}:
            raise ValueError("quote feed must be iex or sip")
        self._client = client
        self.feed = feed

    @classmethod
    def from_environment(
        cls, *, feed: str = "sip", environ: Mapping[str, str] | None = None
    ) -> ReadOnlyAlpacaQuoteDownloader:
        from alpaca.data.historical import StockHistoricalDataClient

        values = os.environ if environ is None else environ
        api_key = values.get(API_KEY_VARIABLE, "")
        secret_key = values.get(SECRET_KEY_VARIABLE, "")
        if not api_key or not secret_key:
            raise RuntimeError(
                f"ALPACA_QUOTE_CREDENTIAL_MISSING: set {API_KEY_VARIABLE} and "
                f"{SECRET_KEY_VARIABLE}"
            )
        client = StockHistoricalDataClient(api_key=api_key, secret_key=secret_key)
        return cls(cast(HistoricalQuotesClient, client), feed=feed)

    def fetch(
        self,
        *,
        symbols: tuple[str, ...],
        start: datetime,
        end: datetime,
        asof: date,
    ) -> pd.DataFrame:
        from alpaca.data.enums import DataFeed
        from alpaca.data.requests import StockQuotesRequest

        if not symbols or tuple(sorted(set(symbols))) != symbols:
            raise ValueError("symbols must be non-empty, unique, and sorted")
        request = StockQuotesRequest(
            symbol_or_symbols=list(symbols),
            start=start,
            end=end,
            feed=DataFeed.SIP if self.feed == "sip" else DataFeed.IEX,
            asof=asof.isoformat(),
        )
        response = self._client.get_stock_quotes(request)
        source = response.df.reset_index()
        if source.empty:
            return pd.DataFrame(columns=QUOTE_COLUMNS)
        missing = sorted(set(QUOTE_COLUMNS).difference(source.columns))
        if missing:
            raise ValueError(f"historical quote schema is missing columns: {missing}")
        frame = source.loc[:, QUOTE_COLUMNS].copy()
        frame["symbol"] = frame["symbol"].astype("string").str.upper()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
        return cast(
            pd.DataFrame,
            frame.sort_values(["symbol", "timestamp"], kind="stable", ignore_index=True),
        )


def latest_quote_features(
    *,
    downloader: ReadOnlyAlpacaQuoteDownloader,
    symbols: tuple[str, ...],
    cutoff: datetime,
    session_date: date,
    sleep: Sleep = time.sleep,
    throttle_seconds: float = 0.35,
) -> pd.DataFrame:
    """Resolve one strictly-causal latest quote per symbol with explicit missing rows."""
    unresolved = set(symbols)
    raw_parts: list[pd.DataFrame] = []
    for seconds in LOOKBACK_SECONDS:
        if not unresolved:
            break
        requested = tuple(sorted(unresolved))
        frame = downloader.fetch(
            symbols=requested,
            start=cutoff - timedelta(seconds=seconds),
            end=cutoff,
            asof=session_date,
        )
        if not frame.empty:
            frame = frame.loc[
                frame["timestamp"].lt(cutoff)
                & frame["bid_price"].gt(0)
                & frame["ask_price"].gt(0)
            ].copy()
            raw_parts.append(frame)
            unresolved.difference_update(frame["symbol"].astype(str).unique())
        if throttle_seconds > 0:
            sleep(throttle_seconds)
    raw = pd.concat(raw_parts, ignore_index=True) if raw_parts else pd.DataFrame()
    if raw.empty:
        latest = pd.DataFrame(columns=QUOTE_COLUMNS)
        latest["symbol"] = latest["symbol"].astype("string")
        counts: dict[str, int] = {}
    else:
        counts = {
            str(symbol): int(count)
            for symbol, count in raw.groupby("symbol", observed=True).size().items()
        }
        latest = raw.sort_values(["symbol", "timestamp"], kind="stable").drop_duplicates(
            "symbol", keep="last"
        )
    requested_frame = pd.DataFrame({"symbol": pd.Series(symbols, dtype="string")})
    result = requested_frame.merge(latest, on="symbol", how="left", validate="one_to_one")
    result["session_date"] = session_date
    result["decision_timestamp"] = pd.Timestamp(cutoff)
    result["quote_available"] = result["timestamp"].notna()
    result["quotes_seen"] = result["symbol"].map(counts).fillna(0).astype("int64")
    result["midpoint"] = (result["bid_price"] + result["ask_price"]) / 2.0
    result["relative_spread"] = (
        (result["ask_price"] - result["bid_price"]) / result["midpoint"]
    )
    size_sum = result["bid_size"] + result["ask_size"]
    result["size_imbalance"] = np.where(
        size_sum.gt(0), (result["bid_size"] - result["ask_size"]) / size_sum, np.nan
    )
    result["quote_age_ms"] = (
        pd.Timestamp(cutoff) - pd.to_datetime(result["timestamp"], utc=True)
    ).dt.total_seconds() * 1000.0
    result["locked_or_crossed"] = result["ask_price"].le(result["bid_price"])
    result["provider"] = "alpaca"
    result["feed"] = downloader.feed
    return result.sort_values("symbol", kind="stable", ignore_index=True)


def acquire_event_quote_features(
    *,
    root: Path,
    events_path: Path,
    downloader: ReadOnlyAlpacaQuoteDownloader,
    start: date,
    end: date,
    batch_size: int = 50,
    sleep: Sleep = time.sleep,
    throttle_seconds: float = 0.35,
) -> list[dict[str, object]]:
    """Acquire quote features for every event symbol, jointly by timestamp and batch."""
    if start > end or end >= BLIND_CUTOFF:
        raise ValueError("quote feature acquisition must stay before the blind cutoff")
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    events = pd.read_parquet(events_path, columns=["symbol", "session_date", "bar_idx"])
    events["session_date"] = pd.to_datetime(events["session_date"]).dt.date
    events = events.loc[events["session_date"].between(start, end)].drop_duplicates()
    events["month"] = events["session_date"].map(lambda value: value.replace(day=1))
    output_root = root.resolve() / "data" / "staging" / f"alpaca_{downloader.feed}_quote_features_v1"
    output_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for month, month_rows in events.groupby("month", observed=True, sort=True):
        month_root = output_root / cast(date, month).strftime("%Y-%m")
        month_root.mkdir(exist_ok=True)
        union = tuple(sorted(month_rows["symbol"].astype(str).unique()))
        for bar_idx in sorted(month_rows["bar_idx"].astype(int).unique()):
            slot_rows = month_rows.loc[month_rows["bar_idx"].eq(bar_idx)]
            for offset in range(0, len(union), batch_size):
                batch = union[offset : offset + batch_size]
                identity = hashlib.sha256(",".join(batch).encode()).hexdigest()[:16]
                stem = f"bar-{bar_idx:02d}-batch-{offset // batch_size:04d}-{identity}"
                parquet = month_root / f"{stem}.parquet"
                manifest_path = month_root / f"{stem}.json"
                if parquet.is_file() and manifest_path.is_file():
                    record = cast(dict[str, object], json.loads(manifest_path.read_text("utf-8")))
                    if record["content_sha256"] != _sha256_file(parquet):
                        raise ValueError(f"quote feature shard hash mismatch: {parquet}")
                    records.append(record)
                    continue
                if parquet.exists() or manifest_path.exists():
                    raise ValueError(f"partial quote feature shard requires audit: {parquet}")
                parts: list[pd.DataFrame] = []
                for session_date, day_rows in slot_rows.groupby(
                    "session_date", observed=True, sort=True
                ):
                    requested = tuple(sorted(set(day_rows["symbol"].astype(str)).intersection(batch)))
                    if not requested:
                        continue
                    session_date = cast(date, session_date)
                    cutoff = decision_timestamp(session_date, int(bar_idx))
                    parts.append(
                        latest_quote_features(
                            downloader=downloader,
                            symbols=requested,
                            cutoff=cutoff,
                            session_date=session_date,
                            sleep=sleep,
                            throttle_seconds=throttle_seconds,
                        )
                    )
                frame = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
                temporary = parquet.with_suffix(".tmp.parquet")
                frame.to_parquet(temporary, index=False, compression="zstd")
                temporary.replace(parquet)
                record = {
                    "schema_version": "1.0.0",
                    "provider": "alpaca",
                    "feed": downloader.feed,
                    "source_type": "historical_quotes",
                    "derived_type": "strictly_prior_latest_quote_features",
                    "month": cast(date, month).isoformat(),
                    "bar_idx": int(bar_idx),
                    "symbols": list(batch),
                    "lookback_seconds": list(LOOKBACK_SECONDS),
                    "requested_rows": len(frame),
                    "available_rows": int(frame.get("quote_available", pd.Series(dtype=bool)).sum()),
                    "missing_rows": int((~frame.get("quote_available", pd.Series(dtype=bool))).sum()),
                    "blind_test_candidate": False,
                    "strategy_metrics_permitted": True,
                    "content_sha256": _sha256_file(parquet),
                }
                with tempfile.NamedTemporaryFile(
                    mode="w", encoding="utf-8", dir=month_root, delete=False
                ) as temporary_manifest:
                    temporary_manifest.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
                    temporary_manifest_path = Path(temporary_manifest.name)
                temporary_manifest_path.replace(manifest_path)
                records.append(record)
    return records
