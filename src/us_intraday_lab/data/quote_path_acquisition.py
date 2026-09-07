"""Read-only fixed-five-second SIP quote-path feature acquisition."""

from __future__ import annotations

import hashlib
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
from us_intraday_lab.data.quote_feature_acquisition import (
    ReadOnlyAlpacaQuoteDownloader,
    _sha256_file,
    decision_timestamp,
)

Sleep = Callable[[float], None]
WINDOW_SECONDS = 5


def aggregate_quote_path_features(
    *, downloader: ReadOnlyAlpacaQuoteDownloader, symbols: tuple[str, ...],
    cutoff: datetime, session_date: date, sleep: Sleep = time.sleep,
    throttle_seconds: float = 0.35,
) -> pd.DataFrame:
    start = cutoff - timedelta(seconds=WINDOW_SECONDS)
    raw = downloader.fetch(symbols=symbols, start=start, end=cutoff, asof=session_date)
    if throttle_seconds > 0:
        sleep(throttle_seconds)
    if not raw.empty:
        raw = raw.loc[
            raw["timestamp"].ge(start) & raw["timestamp"].lt(cutoff)
            & raw["bid_price"].gt(0) & raw["ask_price"].gt(0)
            & raw["bid_size"].ge(0) & raw["ask_size"].ge(0)
        ].sort_values(["symbol", "timestamp"], kind="stable").copy()
        raw["midpoint"] = (raw["bid_price"] + raw["ask_price"]) / 2.0
        raw["relative_spread"] = (raw["ask_price"] - raw["bid_price"]) / raw["midpoint"]
        size_sum = (raw["bid_size"] + raw["ask_size"]).replace(0, np.nan)
        raw["size_imbalance"] = (raw["bid_size"] - raw["ask_size"]) / size_sum
        raw["microprice"] = (
            raw["ask_price"] * raw["bid_size"] + raw["bid_price"] * raw["ask_size"]
        ) / size_sum
        raw["back_half"] = raw["timestamp"].ge(cutoff - timedelta(seconds=2.5)).astype(float)
        raw["locked_or_crossed"] = raw["ask_price"].le(raw["bid_price"]).astype(float)
        for column in ("bid_price", "ask_price", "bid_size", "ask_size"):
            raw[f"{column}_change"] = raw.groupby("symbol", observed=True)[column].diff()
        aggregate = raw.groupby("symbol", as_index=False, observed=True).agg(
            quotes_5s=("midpoint", "size"), first_midpoint=("midpoint", "first"),
            last_midpoint=("midpoint", "last"), high_midpoint=("midpoint", "max"),
            low_midpoint=("midpoint", "min"), first_microprice=("microprice", "first"),
            last_microprice=("microprice", "last"), mean_relative_spread=("relative_spread", "mean"),
            first_relative_spread=("relative_spread", "first"), last_relative_spread=("relative_spread", "last"),
            mean_size_imbalance=("size_imbalance", "mean"), first_size_imbalance=("size_imbalance", "first"),
            last_size_imbalance=("size_imbalance", "last"), back_half_update_share=("back_half", "mean"),
            bid_price_pressure=("bid_price_change", "mean"), ask_price_pressure=("ask_price_change", "mean"),
            bid_size_pressure=("bid_size_change", "mean"), ask_size_pressure=("ask_size_change", "mean"),
            locked_or_crossed_share=("locked_or_crossed", "mean"), last_quote_timestamp=("timestamp", "last"),
        )
    else:
        aggregate = pd.DataFrame({"symbol": pd.Series(dtype="string")})
    result = pd.DataFrame({"symbol": pd.Series(symbols, dtype="string")}).merge(
        aggregate, on="symbol", how="left", validate="one_to_one"
    )
    for column in (
        "quotes_5s", "first_midpoint", "last_midpoint", "high_midpoint", "low_midpoint",
        "first_microprice", "last_microprice", "mean_relative_spread",
        "first_relative_spread", "last_relative_spread", "mean_size_imbalance",
        "first_size_imbalance", "last_size_imbalance", "back_half_update_share",
        "bid_price_pressure", "ask_price_pressure", "bid_size_pressure",
        "ask_size_pressure", "locked_or_crossed_share", "last_quote_timestamp",
    ):
        if column not in result:
            result[column] = np.nan
    result["quote_available"] = result["quotes_5s"].notna()
    result["quotes_5s"] = result["quotes_5s"].fillna(0)
    result["midpoint_return"] = result["last_midpoint"] / result["first_midpoint"] - 1.0
    result["microprice_return"] = result["last_microprice"] / result["first_microprice"] - 1.0
    result["midpoint_range"] = result["high_midpoint"] / result["low_midpoint"] - 1.0
    result["spread_change"] = result["last_relative_spread"] - result["first_relative_spread"]
    result["size_imbalance_change"] = result["last_size_imbalance"] - result["first_size_imbalance"]
    result["last_quote_age_ms"] = (
        pd.Timestamp(cutoff) - pd.to_datetime(result["last_quote_timestamp"], utc=True)
    ).dt.total_seconds() * 1000.0
    result["session_date"] = session_date
    result["decision_timestamp"] = pd.Timestamp(cutoff)
    result["provider"] = "alpaca"
    result["feed"] = downloader.feed
    result["window_seconds"] = WINDOW_SECONDS
    return result.sort_values("symbol", kind="stable", ignore_index=True)


def acquire_event_quote_paths(
    *, root: Path, events_path: Path, downloader: ReadOnlyAlpacaQuoteDownloader,
    start: date, end: date, batch_size: int = 50, sleep: Sleep = time.sleep,
    throttle_seconds: float = 0.35,
) -> list[dict[str, object]]:
    if start > end or end >= BLIND_CUTOFF:
        raise ValueError("quote-path acquisition must stay before the blind cutoff")
    events = pd.read_parquet(events_path, columns=["symbol", "session_date", "bar_idx"])
    events["session_date"] = pd.to_datetime(events["session_date"]).dt.date
    events = events.loc[events["session_date"].between(start, end)].drop_duplicates()
    events["month"] = events["session_date"].map(lambda value: value.replace(day=1))
    output_root = root / "data/staging/alpaca_sip_quote_path_5s_v1"
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
                identity = hashlib.sha256(",".join(batch).encode()).hexdigest()[:16]
                stem = f"bar-{bar_idx:02d}-batch-{offset // batch_size:04d}-{identity}"
                parquet = month_root / f"{stem}.parquet"
                manifest_path = month_root / f"{stem}.json"
                if parquet.is_file() and manifest_path.is_file():
                    record = cast(dict[str, object], json.loads(manifest_path.read_text("utf-8")))
                    if record["content_sha256"] != _sha256_file(parquet):
                        raise ValueError(f"quote-path shard hash mismatch: {parquet}")
                    records.append(record)
                    continue
                if parquet.exists() or manifest_path.exists():
                    raise ValueError(f"partial quote-path shard requires audit: {parquet}")
                parts: list[pd.DataFrame] = []
                for raw_session, day in slot.groupby("session_date", observed=True, sort=True):
                    session = cast(date, raw_session)
                    requested = tuple(sorted(set(day["symbol"].astype(str)).intersection(batch)))
                    if requested:
                        parts.append(aggregate_quote_path_features(
                            downloader=downloader, symbols=requested,
                            cutoff=decision_timestamp(session, int(bar_idx)),
                            session_date=session, sleep=sleep, throttle_seconds=throttle_seconds,
                        ))
                frame = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
                temporary = parquet.with_suffix(".tmp.parquet")
                frame.to_parquet(temporary, index=False, compression="zstd")
                temporary.replace(parquet)
                available = frame.get("quote_available", pd.Series(dtype=bool)).astype(bool)
                record = {
                    "schema_version": "1.0.0", "provider": "alpaca", "feed": "sip",
                    "source_type": "historical_quotes", "window_seconds": WINDOW_SECONDS,
                    "month": month.isoformat(), "bar_idx": int(bar_idx), "symbols": list(batch),
                    "requested_rows": len(frame), "available_rows": int(available.sum()),
                    "missing_rows": int((~available).sum()), "blind_test_candidate": False,
                    "strategy_metrics_permitted": True, "content_sha256": _sha256_file(parquet),
                }
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=month_root, delete=False) as handle:
                    handle.write(json.dumps(record, indent=2, sort_keys=True) + "\n")
                    temporary_manifest = Path(handle.name)
                temporary_manifest.replace(manifest_path)
                records.append(record)
    return records
