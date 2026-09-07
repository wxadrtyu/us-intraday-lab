"""Read-only fixed-30-second SIP trade-path feature acquisition."""

from __future__ import annotations

import json
import tempfile
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

from us_intraday_lab.data.alpaca_iex_acquisition import BLIND_CUTOFF
from us_intraday_lab.data.quote_feature_acquisition import decision_timestamp
from us_intraday_lab.data.trade_feature_acquisition import (
    ReadOnlyAlpacaTradeDownloader,
    _sha256_file,
)

Sleep = Callable[[float], None]
WINDOW_SECONDS = 30


def aggregate_trade_path_features(
    *,
    downloader: ReadOnlyAlpacaTradeDownloader,
    symbols: tuple[str, ...],
    cutoff: datetime,
    session_date: date,
    sleep: Sleep = time.sleep,
    throttle_seconds: float = 0.35,
) -> pd.DataFrame:
    start = cutoff - timedelta(seconds=WINDOW_SECONDS)
    raw = downloader.fetch(symbols=symbols, start=start, end=cutoff, asof=session_date)
    if throttle_seconds > 0:
        sleep(throttle_seconds)
    if not raw.empty:
        raw = raw.loc[
            raw["timestamp"].ge(start)
            & raw["timestamp"].lt(cutoff)
            & raw["price"].gt(0)
            & raw["size"].gt(0)
        ].sort_values(["symbol", "timestamp"], kind="stable").copy()
        raw["notional"] = raw["price"] * raw["size"]
        price_change = raw.groupby("symbol", observed=True)["price"].diff()
        raw["tick_sign"] = np.sign(price_change).replace(0, np.nan)
        raw["tick_sign"] = raw.groupby("symbol", observed=True)["tick_sign"].ffill().fillna(0)
        raw["signed_volume"] = raw["tick_sign"] * raw["size"]
        raw["back_half_volume"] = np.where(
            raw["timestamp"].ge(cutoff - timedelta(seconds=15)), raw["size"], 0.0
        )
        raw["odd_lot_volume"] = np.where(raw["size"] < 100, raw["size"], 0.0)
        aggregate = raw.groupby("symbol", as_index=False, observed=True).agg(
            trades_30s=("price", "size"),
            volume_30s=("size", "sum"),
            notional_30s=("notional", "sum"),
            first_trade_price=("price", "first"),
            last_trade_price=("price", "last"),
            high_trade_price=("price", "max"),
            low_trade_price=("price", "min"),
            largest_trade_size=("size", "max"),
            venue_count=("exchange", "nunique"),
            signed_volume=("signed_volume", "sum"),
            back_half_volume=("back_half_volume", "sum"),
            odd_lot_volume=("odd_lot_volume", "sum"),
        )
        venue = raw.groupby(["symbol", "exchange"], observed=True)["size"].sum()
        venue_max = venue.groupby("symbol").max().rename("largest_venue_volume")
        aggregate = aggregate.merge(venue_max, on="symbol", how="left", validate="one_to_one")
    else:
        aggregate = pd.DataFrame({"symbol": pd.Series(dtype="string")})
    result = pd.DataFrame({"symbol": pd.Series(symbols, dtype="string")}).merge(
        aggregate, on="symbol", how="left", validate="one_to_one"
    )
    columns = (
        "trades_30s", "volume_30s", "notional_30s", "first_trade_price",
        "last_trade_price", "high_trade_price", "low_trade_price",
        "largest_trade_size", "venue_count", "signed_volume",
        "back_half_volume", "odd_lot_volume", "largest_venue_volume",
    )
    for column in columns:
        if column not in result:
            result[column] = np.nan
    result["trade_available"] = result["trades_30s"].notna()
    for column in (
        "trades_30s", "volume_30s", "notional_30s", "venue_count",
        "signed_volume", "back_half_volume", "odd_lot_volume",
        "largest_venue_volume",
    ):
        result[column] = result[column].fillna(0)
    volume = result["volume_30s"].replace(0, np.nan)
    result["trade_vwap_30s"] = result["notional_30s"] / volume
    result["tick_volume_imbalance"] = result["signed_volume"] / volume
    result["back_half_activity_share"] = result["back_half_volume"] / volume
    result["trade_path_return"] = result["last_trade_price"] / result["first_trade_price"] - 1.0
    result["last_to_vwap"] = result["last_trade_price"] / result["trade_vwap_30s"] - 1.0
    result["trade_price_range"] = result["high_trade_price"] / result["low_trade_price"] - 1.0
    result["largest_trade_share"] = result["largest_trade_size"] / volume
    result["venue_concentration"] = result["largest_venue_volume"] / volume
    result["odd_lot_share"] = result["odd_lot_volume"] / volume
    result["session_date"] = session_date
    result["decision_timestamp"] = pd.Timestamp(cutoff)
    result["provider"] = "alpaca"
    result["feed"] = downloader.feed
    result["window_seconds"] = WINDOW_SECONDS
    return result.sort_values("symbol", kind="stable", ignore_index=True)


def acquire_event_trade_paths(
    *, root: Path, events_path: Path, downloader: ReadOnlyAlpacaTradeDownloader,
    start: date, end: date, batch_size: int = 50,
    sleep: Sleep = time.sleep, throttle_seconds: float = 0.35,
) -> list[dict[str, object]]:
    if start > end or end >= BLIND_CUTOFF:
        raise ValueError("trade-path acquisition must stay before the blind cutoff")
    events = pd.read_parquet(events_path, columns=["symbol", "session_date", "bar_idx"])
    events["session_date"] = pd.to_datetime(events["session_date"]).dt.date
    events = events.loc[events["session_date"].between(start, end)].drop_duplicates()
    events["month"] = events["session_date"].map(lambda value: value.replace(day=1))
    output_root = root / "data/staging/alpaca_sip_trade_path_30s_v1"
    output_root.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    for raw_month, month_rows in events.groupby("month", observed=True, sort=True):
        month = cast(date, raw_month)
        month_root = output_root / month.strftime("%Y-%m")
        month_root.mkdir(exist_ok=True)
        union = tuple(sorted(month_rows["symbol"].astype(str).unique()))
        for bar_idx in sorted(month_rows["bar_idx"].astype(int).unique()):
            slot = month_rows.loc[month_rows["bar_idx"].eq(bar_idx)]
            for offset in range(0, len(union), batch_size):
                batch = union[offset : offset + batch_size]
                import hashlib
                identity = hashlib.sha256(",".join(batch).encode()).hexdigest()[:16]
                stem = f"bar-{bar_idx:02d}-batch-{offset // batch_size:04d}-{identity}"
                parquet = month_root / f"{stem}.parquet"
                manifest_path = month_root / f"{stem}.json"
                if parquet.is_file() and manifest_path.is_file():
                    record = cast(dict[str, object], json.loads(manifest_path.read_text("utf-8")))
                    if record["content_sha256"] != _sha256_file(parquet):
                        raise ValueError(f"trade-path shard hash mismatch: {parquet}")
                    records.append(record)
                    continue
                if parquet.exists() or manifest_path.exists():
                    raise ValueError(f"partial trade-path shard requires audit: {parquet}")
                parts: list[pd.DataFrame] = []
                for raw_session, day in slot.groupby("session_date", observed=True, sort=True):
                    session = cast(date, raw_session)
                    requested = tuple(sorted(set(day["symbol"].astype(str)).intersection(batch)))
                    if requested:
                        parts.append(aggregate_trade_path_features(
                            downloader=downloader, symbols=requested,
                            cutoff=decision_timestamp(session, int(bar_idx)),
                            session_date=session, sleep=sleep,
                            throttle_seconds=throttle_seconds,
                        ))
                frame = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
                temporary = parquet.with_suffix(".tmp.parquet")
                frame.to_parquet(temporary, index=False, compression="zstd")
                temporary.replace(parquet)
                available = frame.get("trade_available", pd.Series(dtype=bool)).astype(bool)
                record = {
                    "schema_version": "1.0.0", "provider": "alpaca", "feed": "sip",
                    "source_type": "historical_trades", "window_seconds": WINDOW_SECONDS,
                    "month": month.isoformat(), "bar_idx": int(bar_idx), "symbols": list(batch),
                    "requested_rows": len(frame), "available_rows": int(available.sum()),
                    "missing_rows": int((~available).sum()), "blind_test_candidate": False,
                    "strategy_metrics_permitted": True, "content_sha256": _sha256_file(parquet),
                }
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=month_root, delete=False) as temporary_manifest:
                    temporary_manifest.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
                    temporary_manifest_path = Path(temporary_manifest.name)
                temporary_manifest_path.replace(manifest_path)
                records.append(record)
    return records
