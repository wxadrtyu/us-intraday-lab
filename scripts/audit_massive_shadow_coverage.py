"""Audit Massive SIP minute completeness without writing research-shadow state."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from us_intraday_lab.data.calendar import expected_minute_index

KEY_VARIABLE = "MASSIVE_API_KEY"
BASE_URL = "https://api.massive.com"


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _fetch_symbol(
    *, api_key: str, symbol: str, start: date, end: date, timeout_seconds: float
) -> pd.DataFrame:
    encoded_symbol = urllib.parse.quote(symbol, safe="")
    url = (
        f"{BASE_URL}/v2/aggs/ticker/{encoded_symbol}/range/1/minute/"
        f"{start.isoformat()}/{end.isoformat()}?adjusted=true&sort=asc&limit=50000"
    )
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {api_key}", "User-Agent": "us-intraday-lab/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        retry_after = exc.headers.get("Retry-After", "")
        raise RuntimeError(
            f"MASSIVE_HTTP_ERROR status={exc.code} retry_after={retry_after!r} symbol={symbol}"
        ) from exc
    if payload.get("status") not in {"OK", "DELAYED"}:
        raise RuntimeError(f"MASSIVE_RESPONSE_ERROR symbol={symbol} status={payload.get('status')}")
    if payload.get("next_url"):
        raise RuntimeError(f"MASSIVE_RESPONSE_PAGINATED symbol={symbol}")
    rows = payload.get("results", [])
    frame = pd.DataFrame(rows)
    if frame.empty:
        return pd.DataFrame(
            columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"]
        )
    required = {"t", "o", "h", "l", "c", "v"}
    if not required.issubset(frame.columns):
        raise RuntimeError(f"MASSIVE_SCHEMA_MISMATCH symbol={symbol}")
    return pd.DataFrame(
        {
            "symbol": symbol,
            "timestamp": pd.to_datetime(frame["t"], unit="ms", utc=True),
            "open": frame["o"].astype(float),
            "high": frame["h"].astype(float),
            "low": frame["l"].astype(float),
            "close": frame["c"].astype(float),
            "volume": frame["v"].astype(float),
        }
    )


def _coverage(frame: pd.DataFrame, sessions: tuple[date, ...]) -> dict[str, int]:
    timestamps = pd.DatetimeIndex(frame["timestamp"])
    return {
        session.isoformat(): int(timestamps.isin(expected_minute_index(session)).sum())
        for session in sessions
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal", required=True, type=Path)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--requests-per-minute", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    args = parser.parse_args()
    if args.start > args.end:
        raise ValueError("audit date range is invalid")
    if not 0.0 < args.requests_per_minute <= 5.0:
        raise ValueError("free-plan audit must not exceed five requests per minute")
    api_key = os.environ.get(KEY_VARIABLE, "")
    if not api_key:
        raise RuntimeError("MASSIVE_API_KEY_MISSING")
    proposal = json.loads(args.proposal.read_text(encoding="utf-8"))
    universe = tuple(str(value) for value in proposal["universe"])
    symbols = (*universe, "SPY")
    sessions = tuple(
        session.date()
        for session in pd.date_range(args.start, args.end, freq="D")
        if len(expected_minute_index(session.date())) == 390
    )
    args.cache_dir.mkdir(parents=True, exist_ok=True)
    interval = 60.0 / args.requests_per_minute
    last_request_started: float | None = None
    coverage: dict[str, dict[str, int]] = {}
    sources: dict[str, str] = {}
    for position, symbol in enumerate(symbols, start=1):
        cache = args.cache_dir / f"{symbol.replace('.', '_')}.parquet"
        if cache.exists():
            frame = pd.read_parquet(cache)
            sources[symbol] = "cache"
        else:
            if last_request_started is not None:
                time.sleep(max(0.0, interval - (time.monotonic() - last_request_started)))
            last_request_started = time.monotonic()
            frame = _fetch_symbol(
                api_key=api_key,
                symbol=symbol,
                start=args.start,
                end=args.end,
                timeout_seconds=args.timeout_seconds,
            )
            frame.to_parquet(cache, index=False)
            sources[symbol] = "network"
        coverage[symbol] = _coverage(frame, sessions)
        session_summary: dict[str, Any] = {}
        for session in sessions:
            key = session.isoformat()
            stock_counts = [coverage[item].get(key, 0) for item in universe if item in coverage]
            session_summary[key] = {
                "symbols_audited": len(stock_counts),
                "minimum_stock_minutes_so_far": min(stock_counts) if stock_counts else None,
                "spy_minutes": coverage.get("SPY", {}).get(key),
            }
        checkpoint = {
            "schema_version": "1.0.0",
            "status": "IN_PROGRESS" if position < len(symbols) else "COMPLETE",
            "provider": "massive",
            "feed": "sip_aggregate",
            "date_range": {"start": args.start.isoformat(), "end": args.end.isoformat()},
            "symbols_expected": len(symbols),
            "symbols_audited": position,
            "coverage": coverage,
            "sources": sources,
            "session_summary": session_summary,
        }
        _atomic_json(args.output, checkpoint)
        print(
            json.dumps(
                {"position": position, "symbol": symbol, "coverage": coverage[symbol]},
                sort_keys=True,
            ),
            flush=True,
        )
    final = json.loads(args.output.read_text(encoding="utf-8"))
    final["quality_gate"] = {
        session.isoformat(): {
            "spy_exactly_390": coverage["SPY"][session.isoformat()] == 390,
            "all_stocks_at_least_385": min(
                coverage[symbol][session.isoformat()] for symbol in universe
            )
            >= 385,
            "minimum_stock_minutes": min(
                coverage[symbol][session.isoformat()] for symbol in universe
            ),
            "stocks_below_385": [
                {"symbol": symbol, "minutes": coverage[symbol][session.isoformat()]}
                for symbol in universe
                if coverage[symbol][session.isoformat()] < 385
            ],
        }
        for session in sessions
    }
    _atomic_json(args.output, final)


if __name__ == "__main__":
    main()
