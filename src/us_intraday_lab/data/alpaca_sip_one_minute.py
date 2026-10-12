"""Read-only Alpaca SIP one-minute source with deterministic request identities."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd

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


def load_frozen_candidate_symbols(
    *, assets_path: Path, protocol_path: Path
) -> tuple[str, ...]:
    return _load_frozen_candidate_symbols(
        assets_path=assets_path, protocol_path=protocol_path
    )


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
        unexpected or outside.any() or outside_session.any() or duplicates
        or missing or invalid_ohlc.any() or off_grid.any() or nonfinite
        or bad_trade_count or bad_vwap or source_bad
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
