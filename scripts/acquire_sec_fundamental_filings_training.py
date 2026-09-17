"""Acquire immutable training-only SEC 10-Q facts for the fixed sample."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import pandas as pd

from scripts.acquire_cboe_volatility_training import _sha256, _write_immutable
from us_intraday_lab.data.sec_fundamental_filings import (
    acquire_training_snapshot,
    training_sample_symbols,
)

USER_AGENT = "QuantResearch/1.0 research-team@example.com"


class SecFetcher:
    """Sequential SEC fetcher respecting a four-request-per-second ceiling."""

    def __init__(self) -> None:
        self._last_request = 0.0

    def __call__(self, url: str) -> bytes:
        delay = 0.25 - (time.monotonic() - self._last_request)
        if delay > 0:
            time.sleep(delay)
        for attempt in range(4):
            try:
                request = Request(url, headers={"User-Agent": USER_AGENT})
                with urlopen(request, timeout=60) as response:
                    body = response.read()
                self._last_request = time.monotonic()
                return body
            except HTTPError as error:
                self._last_request = time.monotonic()
                if error.code != 429 and error.code < 500:
                    raise
                if attempt == 3:
                    raise
                time.sleep(2**attempt)
        raise AssertionError("unreachable")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--raw-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    arguments = parser.parse_args()
    symbols = training_sample_symbols(
        pd.read_parquet(arguments.events, columns=["symbol", "session_date"])
    )
    if len(symbols) != 527:
        raise RuntimeError(f"SEC_SAMPLE_SYMBOL_COUNT:{len(symbols)}")
    snapshot, source_manifest = acquire_training_snapshot(
        symbols, SecFetcher(), arguments.raw_root
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.output.with_name(f".{arguments.output.name}.{uuid4().hex}.tmp")
    snapshot.to_parquet(temporary, index=False, compression="zstd")
    try:
        _write_immutable(arguments.output, temporary.read_bytes())
    finally:
        temporary.unlink(missing_ok=True)
    manifest = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        **source_manifest,
        "snapshot_sha256": _sha256(arguments.output),
        "development_or_consumed_returned": False,
        "paper_activation": False,
        "order_route": "FORBIDDEN",
    }
    _write_immutable(
        arguments.manifest,
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
    )
    print(json.dumps(manifest, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
