"""Read-only fixed-window SIP trade-print feature acquisition."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

import numpy as np
import pandas as pd

from us_intraday_lab.data.alpaca_iex_acquisition import (
    API_KEY_VARIABLE,
    BLIND_CUTOFF,
    SECRET_KEY_VARIABLE,
)
from us_intraday_lab.data.quote_feature_acquisition import decision_timestamp

TRADE_COLUMNS = (
    "symbol", "timestamp", "exchange", "price", "size", "id", "conditions", "tape"
)


class HistoricalTradesClient(Protocol):
    def get_stock_trades(self, request: object) -> Any: ...


Sleep = Callable[[float], None]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ReadOnlyAlpacaTradeDownloader:
    def __init__(self, client: HistoricalTradesClient, *, feed: str = "sip") -> None:
        if feed != "sip":
            raise ValueError("v1 trade feature contract requires the SIP feed")
        self._client = client
        self.feed = feed

    @classmethod
    def from_environment(
        cls, *, environ: Mapping[str, str] | None = None
    ) -> ReadOnlyAlpacaTradeDownloader:
        from alpaca.data.historical import StockHistoricalDataClient

        values = os.environ if environ is None else environ
        api_key = values.get(API_KEY_VARIABLE, "")
        secret_key = values.get(SECRET_KEY_VARIABLE, "")
        if not api_key or not secret_key:
            raise RuntimeError(
                f"ALPACA_TRADE_CREDENTIAL_MISSING: set {API_KEY_VARIABLE} and "
                f"{SECRET_KEY_VARIABLE}"
            )
        client = StockHistoricalDataClient(api_key=api_key, secret_key=secret_key)
        return cls(cast(HistoricalTradesClient, client))

    def fetch(
        self, *, symbols: tuple[str, ...], start: datetime, end: datetime, asof: date
    ) -> pd.DataFrame:
        from alpaca.data.enums import DataFeed
        from alpaca.data.requests import StockTradesRequest

        request = StockTradesRequest(
            symbol_or_symbols=list(symbols), start=start, end=end,
            feed=DataFeed.SIP, asof=asof.isoformat(),
        )
        response = self._client.get_stock_trades(request)
        source = response.df.reset_index()
        if source.empty:
            return pd.DataFrame(columns=TRADE_COLUMNS)
        missing = sorted(set(TRADE_COLUMNS).difference(source.columns))
        if missing:
            raise ValueError(f"historical trade schema is missing columns: {missing}")
        frame = source.loc[:, TRADE_COLUMNS].copy()
        frame["symbol"] = frame["symbol"].astype("string").str.upper()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
        return cast(
            pd.DataFrame,
            frame.sort_values(["symbol", "timestamp"], kind="stable", ignore_index=True),
        )


def aggregate_trade_features(
    *,
    downloader: ReadOnlyAlpacaTradeDownloader,
    symbols: tuple[str, ...],
    cutoff: datetime,
    session_date: date,
    midpoint_by_symbol: Mapping[str, float],
    sleep: Sleep = time.sleep,
    throttle_seconds: float = 0.35,
) -> pd.DataFrame:
    raw = downloader.fetch(
        symbols=symbols, start=cutoff - timedelta(seconds=1), end=cutoff, asof=session_date
    )
    if throttle_seconds > 0:
        sleep(throttle_seconds)
    if not raw.empty:
        raw = raw.loc[
            raw["timestamp"].lt(cutoff) & raw["price"].gt(0) & raw["size"].gt(0)
        ].copy()
        raw["notional"] = raw["price"] * raw["size"]
        raw["midpoint"] = raw["symbol"].map(midpoint_by_symbol)
        raw["buy_location_volume"] = np.where(raw["price"] > raw["midpoint"], raw["size"], 0.0)
        raw["sell_location_volume"] = np.where(raw["price"] < raw["midpoint"], raw["size"], 0.0)
        raw["at_mid_volume"] = np.where(raw["price"] == raw["midpoint"], raw["size"], 0.0)
        raw["odd_lot_volume"] = np.where(raw["size"] < 100, raw["size"], 0.0)
        aggregate = raw.groupby("symbol", as_index=False, observed=True).agg(
            trades_1s=("price", "size"),
            volume_1s=("size", "sum"),
            notional_1s=("notional", "sum"),
            last_trade_price=("price", "last"),
            high_trade_price=("price", "max"),
            low_trade_price=("price", "min"),
            largest_trade_size=("size", "max"),
            venue_count=("exchange", "nunique"),
            buy_location_volume=("buy_location_volume", "sum"),
            sell_location_volume=("sell_location_volume", "sum"),
            at_mid_volume=("at_mid_volume", "sum"),
            odd_lot_volume=("odd_lot_volume", "sum"),
        )
    else:
        aggregate = pd.DataFrame({"symbol": pd.Series(dtype="string")})
    result = pd.DataFrame({"symbol": pd.Series(symbols, dtype="string")}).merge(
        aggregate, on="symbol", how="left", validate="one_to_one"
    )
    aggregate_columns = (
        "trades_1s", "volume_1s", "notional_1s", "last_trade_price",
        "high_trade_price", "low_trade_price", "largest_trade_size", "venue_count",
        "buy_location_volume", "sell_location_volume", "at_mid_volume", "odd_lot_volume",
    )
    for column in aggregate_columns:
        if column not in result:
            result[column] = np.nan
    result["trade_available"] = result["trades_1s"].notna()
    for column in (
        "trades_1s", "volume_1s", "notional_1s", "venue_count", "buy_location_volume",
        "sell_location_volume", "at_mid_volume", "odd_lot_volume",
    ):
        result[column] = result[column].fillna(0)
    result["trade_vwap"] = result["notional_1s"] / result["volume_1s"].replace(0, np.nan)
    result["price_range"] = (
        result["high_trade_price"] / result["low_trade_price"] - 1.0
    )
    result["largest_trade_share"] = (
        result["largest_trade_size"] / result["volume_1s"].replace(0, np.nan)
    )
    result["odd_lot_share"] = result["odd_lot_volume"] / result["volume_1s"].replace(0, np.nan)
    classified = result["buy_location_volume"] + result["sell_location_volume"]
    result["trade_location_volume_imbalance"] = (
        (result["buy_location_volume"] - result["sell_location_volume"])
        / classified.replace(0, np.nan)
    )
    midpoint = result["symbol"].map(midpoint_by_symbol)
    result["last_trade_edge_to_midpoint"] = result["last_trade_price"] / midpoint - 1.0
    result["session_date"] = session_date
    result["decision_timestamp"] = pd.Timestamp(cutoff)
    result["provider"] = "alpaca"
    result["feed"] = downloader.feed
    result["window_seconds"] = 1
    return result.sort_values("symbol", kind="stable", ignore_index=True)


def acquire_event_trade_features(
    *, root: Path, events_path: Path, quotes_path: Path,
    downloader: ReadOnlyAlpacaTradeDownloader, start: date, end: date,
    batch_size: int = 50, sleep: Sleep = time.sleep, throttle_seconds: float = 0.35,
) -> list[dict[str, object]]:
    if start > end or end >= BLIND_CUTOFF:
        raise ValueError("trade feature acquisition must stay before the blind cutoff")
    events = pd.read_parquet(events_path, columns=["symbol", "session_date", "bar_idx"])
    quotes = pd.read_parquet(
        quotes_path, columns=["symbol", "session_date", "bar_idx", "midpoint"]
    )
    for frame in (events, quotes):
        frame["session_date"] = pd.to_datetime(frame["session_date"]).dt.date
    events = events.loc[events["session_date"].between(start, end)].drop_duplicates()
    events = events.merge(
        quotes, on=["symbol", "session_date", "bar_idx"], how="left", validate="one_to_one"
    )
    events["month"] = events["session_date"].map(lambda value: value.replace(day=1))
    output_root = root / "data/staging/alpaca_sip_trade_features_1s_v1"
    output_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for month, month_rows in events.groupby("month", observed=True, sort=True):
        month = cast(date, month)
        month_root = output_root / month.strftime("%Y-%m")
        month_root.mkdir(exist_ok=True)
        union = tuple(sorted(month_rows["symbol"].astype(str).unique()))
        for bar_idx in sorted(month_rows["bar_idx"].astype(int).unique()):
            slot = month_rows.loc[month_rows["bar_idx"].eq(bar_idx)]
            for offset in range(0, len(union), batch_size):
                batch = union[offset : offset + batch_size]
                identity = hashlib.sha256(",".join(batch).encode()).hexdigest()[:16]
                stem = f"bar-{bar_idx:02d}-batch-{offset // batch_size:04d}-{identity}"
                parquet = month_root / f"{stem}.parquet"
                manifest_path = month_root / f"{stem}.json"
                if parquet.is_file() and manifest_path.is_file():
                    record = cast(dict[str, object], json.loads(manifest_path.read_text("utf-8")))
                    if record["content_sha256"] != _sha256_file(parquet):
                        raise ValueError(f"trade shard hash mismatch: {parquet}")
                    records.append(record)
                    continue
                if parquet.exists() or manifest_path.exists():
                    raise ValueError(f"partial trade shard requires audit: {parquet}")
                parts: list[pd.DataFrame] = []
                for session_date, day in slot.groupby("session_date", observed=True, sort=True):
                    requested = tuple(sorted(set(day["symbol"].astype(str)).intersection(batch)))
                    if not requested:
                        continue
                    midpoint = {
                        str(symbol): float(value)
                        for symbol, value in day.set_index("symbol")["midpoint"].items()
                    }
                    parts.append(aggregate_trade_features(
                        downloader=downloader, symbols=requested,
                        cutoff=decision_timestamp(cast(date, session_date), int(bar_idx)),
                        session_date=cast(date, session_date), midpoint_by_symbol=midpoint,
                        sleep=sleep, throttle_seconds=throttle_seconds,
                    ))
                frame = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
                temporary = parquet.with_suffix(".tmp.parquet")
                frame.to_parquet(temporary, index=False, compression="zstd")
                temporary.replace(parquet)
                record = {
                    "schema_version": "1.0.0", "provider": "alpaca", "feed": "sip",
                    "source_type": "historical_trades", "window_seconds": 1,
                    "month": month.isoformat(), "bar_idx": int(bar_idx), "symbols": list(batch),
                    "requested_rows": len(frame),
                    "available_rows": int(frame.get("trade_available", pd.Series(dtype=bool)).sum()),
                    "missing_rows": int((~frame.get("trade_available", pd.Series(dtype=bool))).sum()),
                    "blind_test_candidate": False, "strategy_metrics_permitted": True,
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
