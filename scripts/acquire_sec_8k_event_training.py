"""Acquire immutable SEC submissions history for structured 8-K training."""

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

from us_intraday_lab.data.sec_8k_events import (
    normalize_8k_filings,
    select_training_fragments,
)
from us_intraday_lab.data.sec_fundamental_filings import (
    parse_ticker_map,
    training_sample_symbols,
)

BASE_URL = "https://data.sec.gov/submissions/"
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
                raise RuntimeError(f"SEC_8K_OUTPUT_IMMUTABLE_COLLISION:{path}")
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


def _current_sources(manifest: dict[str, object]) -> dict[str, dict[str, object]]:
    if manifest.get("status") != "COMPLETE":
        raise RuntimeError("SEC_8K_CURRENT_MANIFEST_INCOMPLETE")
    result: dict[str, dict[str, object]] = {}
    for source in manifest.get("sources", []):
        if not isinstance(source, dict):
            continue
        url = str(source.get("url", ""))
        filename = url.rsplit("/", 1)[-1]
        if url.startswith(BASE_URL) and filename.startswith("CIK") and filename.endswith(
            ".json"
        ):
            result[filename] = source
    return result


def _resume_complete(
    root: Path, manifest: dict[str, object]
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    for source in manifest["sources"]:
        raw_path = Path(str(source["raw_path"]))
        if not raw_path.exists() or _sha256(raw_path) != source["sha256"]:
            raise RuntimeError(f"SEC_8K_RAW_IMMUTABLE_COLLISION:{raw_path}")
    snapshot_path = root / "sec_8k_event_training_v1.parquet"
    rejection_path = root / "rejections.parquet"
    if not snapshot_path.exists() or _sha256(snapshot_path) != manifest["snapshot_sha256"]:
        raise RuntimeError("SEC_8K_SNAPSHOT_IMMUTABLE_COLLISION")
    if not rejection_path.exists() or _sha256(rejection_path) != manifest["rejections_sha256"]:
        raise RuntimeError("SEC_8K_REJECTIONS_IMMUTABLE_COLLISION")
    return pd.read_parquet(snapshot_path), pd.read_parquet(rejection_path), manifest


def acquire_training_snapshot(
    *,
    fetch: Fetch,
    root: Path,
    identities: pd.DataFrame,
    current_root: Path,
    current_manifest: dict[str, object],
    request_interval: float = 0.25,
    unmatched_symbols: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Reuse verified current submissions and fetch only declared history."""
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("status") == "COMPLETE":
            return _resume_complete(root, manifest)
    expected_current = _current_sources(current_manifest)
    responses: list[tuple[str, dict[str, object]]] = []
    sources: list[dict[str, object]] = []
    last_request = 0.0
    for cik in sorted(pd.to_numeric(identities["cik"]).astype("int64").unique()):
        filename = f"CIK{cik:010d}.json"
        path = current_root / filename
        evidence = expected_current.get(filename)
        if evidence is None or not path.exists() or _sha256(path) != evidence.get("sha256"):
            raise RuntimeError(f"SEC_8K_CURRENT_HASH_MISMATCH:{filename}")
        current_body = path.read_bytes()
        current_payload = json.loads(current_body)
        responses.append((str(evidence["url"]), current_payload))
        sources.append(
            {
                "url": evidence["url"],
                "raw_path": str(path.resolve()),
                "bytes": len(current_body),
                "sha256": _sha256_bytes(current_body),
                "reused_current": True,
            }
        )
        for fragment_name in select_training_fragments(
            current_payload, pd.Timestamp("2021-01-01").date(), pd.Timestamp("2023-12-31").date()
        ):
            url = f"{BASE_URL}{fragment_name}"
            fragment_path = root / "raw" / "historical" / fragment_name
            if fragment_path.exists():
                body = fragment_path.read_bytes()
            else:
                delay = request_interval - (time.monotonic() - last_request)
                if delay > 0:
                    time.sleep(delay)
                body = fetch(url)
                last_request = time.monotonic()
                _atomic_write(fragment_path, body)
            fragment = json.loads(body)
            responses.append((url, {"cik": str(cik), "recent": fragment}))
            sources.append(
                {
                    "url": url,
                    "raw_path": str(fragment_path.resolve()),
                    "bytes": len(body),
                    "sha256": _sha256_bytes(body),
                    "reused_current": False,
                }
            )
    filings, rejected = normalize_8k_filings(responses, identities)
    snapshot_path = root / "sec_8k_event_training_v1.parquet"
    rejection_path = root / "rejections.parquet"
    _atomic_parquet(snapshot_path, filings)
    _atomic_parquet(rejection_path, rejected)
    years = sorted({value.year for value in filings.get("filing_date", [])})
    manifest = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "training_only": True,
        "requested_symbols": int(identities["symbol"].nunique())
        + len(unmatched_symbols or []),
        "matched_symbols": int(identities["symbol"].nunique()),
        "unmatched_symbols": sorted(unmatched_symbols or []),
        "unique_ciks": int(identities["cik"].nunique()),
        "sources": sources,
        "required_sources_complete": True,
        "normalized_symbol_filings": len(filings),
        "normalized_issuers": int(filings["cik"].nunique()) if not filings.empty else 0,
        "training_years": years,
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


class SecSubmissionsFetcher:
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
    parser.add_argument("--current-root", required=True, type=Path)
    parser.add_argument("--current-manifest", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    arguments = parser.parse_args()
    events = pd.read_parquet(arguments.events, columns=["symbol", "session_date"])
    symbols = training_sample_symbols(events)
    if len(symbols) != 527:
        raise RuntimeError(f"SEC_8K_SAMPLE_SYMBOL_COUNT:{len(symbols)}")
    identities, missing = parse_ticker_map(arguments.ticker_map.read_bytes(), symbols)
    _filings, _rejected, manifest = acquire_training_snapshot(
        fetch=SecSubmissionsFetcher(),
        root=arguments.root,
        identities=identities,
        current_root=arguments.current_root,
        current_manifest=json.loads(arguments.current_manifest.read_text(encoding="utf-8")),
        unmatched_symbols=missing["symbol"].astype(str).tolist(),
    )
    print(json.dumps(manifest, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
