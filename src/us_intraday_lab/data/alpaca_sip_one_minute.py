"""Read-only Alpaca SIP one-minute source with deterministic request identities."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from us_intraday_lab.data.alpaca_sip_five_minute import (
    load_frozen_candidate_symbols as _load_frozen_candidate_symbols,
)

API_KEY_VARIABLE = "ALPACA_PAPER_API_KEY"
SECRET_KEY_VARIABLE = "ALPACA_PAPER_SECRET_KEY"
SIP_ONE_MINUTE_NAMESPACE = "alpaca_sip_1min_v1"


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
        frame = self._client.get_stock_bars(request).df.reset_index()
        if frame.empty:
            return pd.DataFrame(
                columns=(
                    "symbol", "timestamp", "open", "high", "low", "close",
                    "volume", "trade_count", "vwap", "asof", "provider", "feed",
                )
            )
        result = frame.copy()
        result["symbol"] = result["symbol"].astype(str).str.upper()
        result["timestamp"] = pd.to_datetime(result["timestamp"], utc=True)
        result["asof"] = asof
        result["provider"] = "alpaca"
        result["feed"] = "sip"
        result.attrs["provider_source_rows"] = len(result)
        return result


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
