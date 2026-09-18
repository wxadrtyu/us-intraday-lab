"""Build causal SEC 8-K event features for the frozen training sample."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import pandas as pd

from us_intraday_lab.data.sec_8k_events import build_event_features
from us_intraday_lab.data.sec_fundamental_filings import parse_ticker_map


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--filings", required=True, type=Path)
    parser.add_argument("--ticker-map", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    events = pd.read_parquet(
        arguments.events, columns=["symbol", "session_date", "bar_idx"]
    )
    filings = pd.read_parquet(arguments.filings)
    identities, _missing = parse_ticker_map(
        arguments.ticker_map.read_bytes(), set(events["symbol"].astype(str))
    )
    result = build_event_features(events, filings, identities)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.output.with_name(
        f".{arguments.output.name}.{uuid4().hex}.tmp"
    )
    result.to_parquet(temporary, index=False, compression="zstd")
    try:
        if arguments.output.exists():
            if arguments.output.read_bytes() != temporary.read_bytes():
                raise RuntimeError("SEC_8K_FEATURE_IMMUTABLE_COLLISION")
        else:
            temporary.replace(arguments.output)
    finally:
        temporary.unlink(missing_ok=True)
    inventory = (
        filings[["symbol", "cik", "accession_number"]]
        .drop_duplicates()
        .groupby(["symbol", "cik"], observed=True)
        .size()
    )
    summary = {
        "status": "COMPLETE",
        "training_only": True,
        "rows": len(result),
        "categorized_symbol_filings": len(filings),
        "issuers_with_three_categorized_filings": int(inventory.ge(3).sum()),
        "filing_years": sorted(
            pd.to_datetime(filings["filing_date"]).dt.year.unique().tolist()
        ),
        "coverage_reasons": {
            str(key): int(value)
            for key, value in result["coverage_reason"].value_counts().items()
        },
        "output_sha256": _sha256(arguments.output),
        "development_or_consumed_loaded": False,
        "paper_activation": False,
        "order_route": "FORBIDDEN",
    }
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
