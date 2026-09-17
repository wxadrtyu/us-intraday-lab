"""Build causal event features from the training-only CFTC snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from scripts.acquire_cboe_volatility_training import _sha256
from us_intraday_lab.data.cftc_positioning import build_event_features


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--positions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    events = pd.read_parquet(
        arguments.events, columns=["symbol", "session_date", "bar_idx"]
    )
    features = build_event_features(events, pd.read_parquet(arguments.positions))
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.output.with_suffix(".tmp.parquet")
    features.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(arguments.output)
    summary = {
        "status": "COMPLETE",
        "training_only": True,
        "rows": len(features),
        "covered_rows": int(features["coverage_reason"].eq("COVERED").sum()),
        "coverage_reasons": {
            str(key): int(value)
            for key, value in features["coverage_reason"].value_counts().items()
        },
        "output_sha256": _sha256(arguments.output),
    }
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
