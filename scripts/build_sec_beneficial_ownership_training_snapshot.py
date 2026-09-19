"""Build an immutable Schedule 13D/13G snapshot from frozen SEC sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from uuid import uuid4

import pandas as pd

from us_intraday_lab.data.sec_beneficial_ownership import normalize_filings
from us_intraday_lab.data.sec_fundamental_filings import (
    parse_ticker_map,
    training_sample_symbols,
)


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
                raise RuntimeError(
                    f"SEC_BENEFICIAL_OUTPUT_IMMUTABLE_COLLISION:{path}"
                )
        else:
            temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_parquet(path: Path, frame: pd.DataFrame) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(temporary, index=False, compression="zstd")
    try:
        _atomic_write(path, temporary.read_bytes())
    finally:
        temporary.unlink(missing_ok=True)


def _resume(
    root: Path, manifest: dict[str, object]
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    for source in manifest["sources"]:
        path = Path(str(source["raw_path"]))
        if not path.exists() or _sha256(path) != source["sha256"]:
            raise RuntimeError(f"SEC_BENEFICIAL_SOURCE_HASH_MISMATCH:{path}")
    snapshot_path = root / "sec_beneficial_ownership_training_v1.parquet"
    rejection_path = root / "rejections.parquet"
    if _sha256(snapshot_path) != manifest["snapshot_sha256"]:
        raise RuntimeError("SEC_BENEFICIAL_SNAPSHOT_IMMUTABLE_COLLISION")
    if _sha256(rejection_path) != manifest["rejections_sha256"]:
        raise RuntimeError("SEC_BENEFICIAL_REJECTIONS_IMMUTABLE_COLLISION")
    return pd.read_parquet(snapshot_path), pd.read_parquet(rejection_path), manifest


def build_snapshot(
    source_manifest: dict[str, object],
    identities: pd.DataFrame,
    root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Verify canonical SEC bytes, normalize schedules, and publish atomically."""
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("status") == "COMPLETE":
            return _resume(root, existing)
    if (
        source_manifest.get("status") != "COMPLETE"
        or source_manifest.get("required_sources_complete") is not True
    ):
        raise RuntimeError("SEC_BENEFICIAL_SOURCE_MANIFEST_INCOMPLETE")
    responses: list[tuple[str, int, dict[str, object]]] = []
    verified_sources: list[dict[str, object]] = []
    for source in source_manifest.get("sources", []):
        path = Path(str(source["raw_path"]))
        body = path.read_bytes() if path.exists() else b""
        if _sha256_bytes(body) != source.get("sha256"):
            raise RuntimeError(f"SEC_BENEFICIAL_SOURCE_HASH_MISMATCH:{path}")
        filename = str(source["url"]).rsplit("/", 1)[-1]
        match = re.fullmatch(r"CIK(\d{10})(?:-submissions-\d+)?\.json", filename)
        if match is None:
            raise RuntimeError(f"SEC_BENEFICIAL_SOURCE_NAME_INVALID:{filename}")
        cik = int(match.group(1))
        payload = json.loads(body)
        responses.append((str(source["url"]), cik, payload))
        verified_sources.append(
            {
                "url": source["url"],
                "raw_path": str(path.resolve()),
                "bytes": len(body),
                "sha256": source["sha256"],
            }
        )
    filings, rejected = normalize_filings(responses, identities)
    snapshot_path = root / "sec_beneficial_ownership_training_v1.parquet"
    rejection_path = root / "rejections.parquet"
    _atomic_parquet(snapshot_path, filings)
    _atomic_parquet(rejection_path, rejected)
    manifest = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "training_only": True,
        "source_hashes_verified": True,
        "sources": verified_sources,
        "requested_symbols": int(identities["symbol"].nunique())
        + len(source_manifest.get("unmatched_symbols", [])),
        "matched_symbols": int(identities["symbol"].nunique()),
        "unmatched_symbols": sorted(source_manifest.get("unmatched_symbols", [])),
        "normalized_symbol_filings": len(filings),
        "normalized_ciks": int(filings["cik"].nunique()) if not filings.empty else 0,
        "training_years": sorted(
            pd.to_datetime(filings["filing_date"]).dt.year.unique().tolist()
        )
        if not filings.empty
        else [],
        "rejected_rows": len(rejected),
        "snapshot_sha256": _sha256(snapshot_path),
        "rejections_sha256": _sha256(rejection_path),
        "development_or_consumed_loaded": False,
        "paper_activation": False,
        "order_route": "FORBIDDEN",
    }
    _atomic_write(
        manifest_path,
        (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode(),
    )
    return filings, rejected, manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--ticker-map", required=True, type=Path)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    arguments = parser.parse_args()
    events = pd.read_parquet(arguments.events, columns=["symbol", "session_date"])
    symbols = training_sample_symbols(events)
    if len(symbols) != 527:
        raise RuntimeError(f"SEC_BENEFICIAL_SAMPLE_SYMBOL_COUNT:{len(symbols)}")
    identities, _missing = parse_ticker_map(arguments.ticker_map.read_bytes(), symbols)
    _filings, _rejected, manifest = build_snapshot(
        json.loads(arguments.source_manifest.read_text(encoding="utf-8")),
        identities,
        arguments.root,
    )
    print(json.dumps(manifest, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
