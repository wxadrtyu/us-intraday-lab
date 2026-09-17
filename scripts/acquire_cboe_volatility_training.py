"""Acquire an immutable training-only Cboe volatility-index snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from us_intraday_lab.data.cboe_volatility_regime import build_training_snapshot


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fetch(url: str) -> bytes:
    request = Request(url, headers={"User-Agent": "us-intraday-lab-research/1.0"})
    for attempt in range(5):
        try:
            with urlopen(request, timeout=30) as response:
                return response.read()
        except (URLError, TimeoutError):
            if attempt == 4:
                raise
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError("CBOE_FETCH_UNREACHABLE")


def _write_immutable(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != content:
            raise RuntimeError(f"CBOE_IMMUTABLE_COLLISION:{path}")
        return
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    arguments = parser.parse_args()
    snapshot, sources = build_training_snapshot(_fetch)
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
        "training_only": True,
        "period": "2021-01-01/2023-12-31",
        "rows": len(snapshot),
        "source_date_min": snapshot["source_date"].min().isoformat(),
        "source_date_max": snapshot["source_date"].max().isoformat(),
        "snapshot_sha256": _sha256(arguments.output),
        "sources": sources,
        "development_or_consumed_persisted": False,
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
