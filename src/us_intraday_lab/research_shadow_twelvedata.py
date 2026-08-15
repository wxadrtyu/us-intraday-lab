"""Read-only Twelve Data history adapter for broker-free research shadow."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pandas as pd

KEY_VARIABLE = "TWELVEDATA_API_KEY"
BASE_URL = "https://api.twelvedata.com/time_series"
RequestJson = Callable[[dict[str, str], str, float], dict[str, Any]]


def _request_json(parameters: dict[str, str], api_key: str, timeout: float) -> dict[str, Any]:
    query = urllib.parse.urlencode({**parameters, "apikey": api_key})
    request = urllib.request.Request(
        f"{BASE_URL}?{query}", headers={"User-Agent": "us-intraday-lab/0.1"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return cast(dict[str, Any], json.loads(response.read()))
    except urllib.error.HTTPError as exc:
        retry_after = exc.headers.get("Retry-After", "")
        raise RuntimeError(
            f"TWELVEDATA_HTTP_ERROR status={exc.code} retry_after={retry_after!r}"
        ) from exc


class TwelveDataHistory:
    """Fetch minute bars only; this adapter has no trading or order dependency."""

    def __init__(
        self,
        api_key: str,
        *,
        request_json: RequestJson = _request_json,
        requests_per_minute: float = 8.0,
        timeout_seconds: float = 30.0,
        sleeper: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not api_key:
            raise ValueError("Twelve Data API key cannot be empty")
        if requests_per_minute <= 0.0:
            raise ValueError("Twelve Data request rate must be positive")
        self._api_key = api_key
        self._request_json = request_json
        self._interval = 60.0 / requests_per_minute
        self._timeout_seconds = timeout_seconds
        self._sleeper = sleeper
        self._monotonic = monotonic
        self._last_request_started: float | None = None

    @classmethod
    def from_environment(
        cls,
        *,
        environ: Mapping[str, str] | None = None,
        **kwargs: Any,
    ) -> TwelveDataHistory:
        values = os.environ if environ is None else environ
        api_key = values.get(KEY_VARIABLE, "")
        if not api_key:
            raise RuntimeError("TWELVEDATA_MARKET_DATA_CREDENTIAL_MISSING")
        return cls(api_key, **kwargs)

    def _request(self, parameters: dict[str, str]) -> dict[str, Any]:
        if self._last_request_started is not None:
            elapsed = self._monotonic() - self._last_request_started
            self._sleeper(max(0.0, self._interval - elapsed))
        self._last_request_started = self._monotonic()
        payload = self._request_json(parameters, self._api_key, self._timeout_seconds)
        if payload.get("status") == "error":
            raise RuntimeError(
                f"TWELVEDATA_RESPONSE_ERROR code={payload.get('code')} "
                f"message={payload.get('message')!r}"
            )
        return payload

    def fetch(
        self,
        *,
        symbols: tuple[str, ...],
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        if not symbols or len(symbols) != len(set(symbols)):
            raise ValueError("research shadow symbols must be non-empty and unique")
        if start.utcoffset() is None or end.utcoffset() is None or start >= end:
            raise ValueError("research shadow history bounds are invalid")
        frames: list[pd.DataFrame] = []
        for symbol in symbols:
            cursor = start.astimezone(UTC)
            while cursor < end.astimezone(UTC):
                chunk_end = min(cursor + timedelta(days=16), end.astimezone(UTC))
                payload = self._request(
                    {
                        "symbol": symbol,
                        "interval": "1min",
                        "start_date": cursor.strftime("%Y-%m-%d %H:%M:%S"),
                        "end_date": chunk_end.strftime("%Y-%m-%d %H:%M:%S"),
                        "timezone": "UTC",
                        "order": "ASC",
                        "outputsize": "5000",
                    }
                )
                values = payload.get("values", [])
                if values:
                    frame = pd.DataFrame(values)
                    required = {"datetime", "open", "high", "low", "close", "volume"}
                    if not required.issubset(frame.columns):
                        raise RuntimeError(f"TWELVEDATA_SCHEMA_MISMATCH symbol={symbol}")
                    frames.append(
                        pd.DataFrame(
                            {
                                "symbol": symbol,
                                "timestamp": pd.to_datetime(frame["datetime"], utc=True),
                                "open": frame["open"].astype(float),
                                "high": frame["high"].astype(float),
                                "low": frame["low"].astype(float),
                                "close": frame["close"].astype(float),
                                "volume": frame["volume"].astype(float),
                            }
                        )
                    )
                cursor = chunk_end
        if not frames:
            raise RuntimeError("TWELVEDATA_HISTORY_EMPTY")
        result = pd.concat(frames, ignore_index=True)
        result = result.drop_duplicates(["symbol", "timestamp"], keep="last")
        return result.sort_values(["timestamp", "symbol"]).reset_index(drop=True)
