"""Build causal event features from the training-only Cboe snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from us_intraday_lab.data.cboe_volatility_regime import build_event_features


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--indices", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    events = pd.read_parquet(
        arguments.events, columns=["symbol", "session_date", "bar_idx"]
    )
    indices = pd.read_parquet(arguments.indices)
    features = build_event_features(events, indices)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.output.with_suffix(".tmp.parquet")
    features.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(arguments.output)
    summary = {
        "status": "COMPLETE",
        "training_only": True,
        "rows": len(features),
        "unique_event_keys": int(
            features[["symbol", "session_date", "bar_idx"]].drop_duplicates().shape[0]
        ),
        "covered_rows": int(features["coverage_reason"].eq("COVERED").sum()),
        "output_sha256": _sha256(arguments.output),
    }
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
