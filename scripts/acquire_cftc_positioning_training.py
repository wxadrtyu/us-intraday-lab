"""Acquire an immutable training-only CFTC TFF positioning snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import uuid4

from scripts.acquire_cboe_volatility_training import _fetch, _sha256, _write_immutable
from us_intraday_lab.data.cftc_positioning import build_training_snapshot


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    arguments = parser.parse_args()
    snapshot, source_manifest = build_training_snapshot(_fetch)
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
