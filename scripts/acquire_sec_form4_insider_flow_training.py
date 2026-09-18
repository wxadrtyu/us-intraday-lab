"""Acquire immutable SEC Form 4 bulk files for the frozen training sample."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

import pandas as pd

from us_intraday_lab.data.sec_form4_insider_flow import (
    normalize_form4_filings,
    parse_quarter_zip,
    quarter_urls,
)
from us_intraday_lab.data.sec_fundamental_filings import (
    parse_ticker_map,
    training_sample_symbols,
)

USER_AGENT = "QuantResearch/1.0 research-team@example.com"
Fetch = Callable[[str], bytes]


def _sha256_bytes(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _sha256(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _atomic_write(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_bytes(body)
    try:
        if path.exists():
            if path.read_bytes() != body:
                raise RuntimeError(f"SEC_FORM4_OUTPUT_IMMUTABLE_COLLISION:{path}")
        else:
            temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_parquet(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    frame.to_parquet(temporary, index=False, compression="zstd")
    try:
        _atomic_write(path, temporary.read_bytes())
    finally:
        temporary.unlink(missing_ok=True)


def _resume_complete(
    root: Path, manifest: dict[str, object]
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    for source in manifest["sources"]:
        raw_path = Path(str(source["raw_path"]))
        if not raw_path.exists() or _sha256(raw_path) != source["sha256"]:
            raise RuntimeError(f"SEC_FORM4_RAW_IMMUTABLE_COLLISION:{raw_path}")
    snapshot_path = root / "sec_form4_insider_flow_training_v1.parquet"
    rejection_path = root / "rejections.parquet"
    if _sha256(snapshot_path) != manifest["snapshot_sha256"]:
        raise RuntimeError("SEC_FORM4_SNAPSHOT_IMMUTABLE_COLLISION")
    if _sha256(rejection_path) != manifest["rejections_sha256"]:
        raise RuntimeError("SEC_FORM4_REJECTIONS_IMMUTABLE_COLLISION")
    return (
        pd.read_parquet(snapshot_path),
        pd.read_parquet(rejection_path),
        manifest,
    )


def acquire_training_snapshot(
    *,
    fetch: Fetch,
    root: Path,
    identities: pd.DataFrame,
    request_interval: float = 0.25,
    unmatched_symbols: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Acquire, normalize, and atomically publish all 12 training quarters."""
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") == "COMPLETE":
            return _resume_complete(root, manifest)
    raw_root = root / "raw"
    parsed: list[dict[str, pd.DataFrame]] = []
    sources: list[dict[str, object]] = []
    last_request = 0.0
    for url in quarter_urls():
        filename = url.rsplit("/", 1)[-1]
        path = raw_root / filename
        if path.exists():
            body = path.read_bytes()
        else:
            delay = request_interval - (time.monotonic() - last_request)
            if delay > 0:
                time.sleep(delay)
            body = fetch(url)
            last_request = time.monotonic()
            _atomic_write(path, body)
        parsed.append(parse_quarter_zip(body, filename))
        sources.append(
            {
                "url": url,
                "raw_path": str(path.resolve()),
                "bytes": len(body),
                "sha256": _sha256_bytes(body),
                "table_rows": {
                    key: len(frame) for key, frame in parsed[-1].items()
                },
            }
        )
    tables = {
        key: pd.concat([quarter[key] for quarter in parsed], ignore_index=True)
        for key in ("submission", "reportingowner", "nonderiv_trans")
    }
    if tables["submission"].duplicated("ACCESSION_NUMBER").any():
        raise ValueError("SEC_FORM4_SUBMISSION_KEY_DUPLICATE_ACROSS_QUARTERS")
    if tables["reportingowner"].duplicated(
        ["ACCESSION_NUMBER", "RPTOWNERCIK"]
    ).any():
        raise ValueError("SEC_FORM4_OWNER_KEY_DUPLICATE_ACROSS_QUARTERS")
    if tables["nonderiv_trans"].duplicated(
        ["ACCESSION_NUMBER", "NONDERIV_TRANS_SK"]
    ).any():
        raise ValueError("SEC_FORM4_TRANSACTION_KEY_DUPLICATE_ACROSS_QUARTERS")
    filings, rejected = normalize_form4_filings(tables, identities)
    snapshot_path = root / "sec_form4_insider_flow_training_v1.parquet"
    rejection_path = root / "rejections.parquet"
    _atomic_parquet(snapshot_path, filings)
    _atomic_parquet(rejection_path, rejected)
    manifest = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "training_only": True,
        "requested_symbols": int(identities["symbol"].nunique())
        + len(unmatched_symbols or []),
        "matched_symbols": int(identities["symbol"].nunique()),
        "unmatched_symbols": sorted(unmatched_symbols or []),
        "sources": sources,
        "normalized_filings": len(filings),
        "normalized_issuers": int(filings["symbol"].nunique()),
        "rejected_rows": len(rejected),
        "snapshot_sha256": _sha256(snapshot_path),
        "rejections_sha256": _sha256(rejection_path),
        "development_or_consumed_returned": False,
        "paper_activation": False,
        "order_route": "FORBIDDEN",
    }
    _atomic_write(
        manifest_path,
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
    )
    return filings, rejected, manifest


class SecBulkFetcher:
    """Bounded-retry official SEC fetcher."""

    def __call__(self, url: str) -> bytes:
        for attempt in range(4):
            try:
                request = Request(url, headers={"User-Agent": USER_AGENT})
                with urlopen(request, timeout=120) as response:
                    return response.read()
            except HTTPError as error:
                if (error.code != 429 and error.code < 500) or attempt == 3:
                    raise
            except URLError:
                if attempt == 3:
                    raise
            time.sleep(2**attempt)
        raise AssertionError("unreachable")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--ticker-map", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    arguments = parser.parse_args()
    events = pd.read_parquet(
        arguments.events, columns=["symbol", "session_date"]
    )
    symbols = training_sample_symbols(events)
    if len(symbols) != 527:
        raise RuntimeError(f"SEC_FORM4_SAMPLE_SYMBOL_COUNT:{len(symbols)}")
    identities, missing = parse_ticker_map(
        arguments.ticker_map.read_bytes(), symbols
    )
    _filings, _rejected, manifest = acquire_training_snapshot(
        fetch=SecBulkFetcher(),
        root=arguments.root,
        identities=identities,
        unmatched_symbols=missing["symbol"].astype(str).tolist(),
    )
    print(json.dumps(manifest, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
