"""Build causal event features from the frozen SEC 10-Q snapshot."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from scripts.acquire_cboe_volatility_training import _sha256
from us_intraday_lab.data.sec_fundamental_filings import (
    build_event_features,
    derive_filing_features,
    parse_ticker_map,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--ticker-map", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    events = pd.read_parquet(
        arguments.events, columns=["symbol", "session_date", "bar_idx"]
    )
    snapshot = pd.read_parquet(arguments.snapshot)
    filings = snapshot[
        ["symbol", "cik", "accession", "filing_date", "report_date"]
    ].drop_duplicates()
    facts = snapshot[
        ["cik", "accession", "concept", "start_date", "end_date", "value"]
    ].drop_duplicates()
    filing_features = derive_filing_features(filings, facts)
    identity, _missing = parse_ticker_map(
        arguments.ticker_map.read_bytes(), set(events["symbol"].astype(str))
    )
    result = build_event_features(events, filing_features, identity)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = arguments.output.with_suffix(".tmp.parquet")
    result.to_parquet(temporary, index=False, compression="zstd")
    temporary.replace(arguments.output)
    feature_columns = [
        "revenue_growth_acceleration",
        "gross_margin_expansion",
        "operating_margin_expansion",
        "cash_asset_improvement",
        "deleveraging",
    ]
    summary = {
        "status": "COMPLETE",
        "training_only": True,
        "rows": len(result),
        "filing_feature_events": len(filing_features),
        "issuers_with_four_feature_events": int(
            filing_features.loc[filing_features[feature_columns].notna().any(axis=1)]
            .groupby("symbol", observed=True)
            .size()
            .ge(4)
            .sum()
        ),
        "feature_bearing_events": int(
            filing_features[feature_columns].notna().any(axis=1).sum()
        ),
        "coverage_reasons": {
            str(key): int(value)
            for key, value in result["coverage_reason"].value_counts().items()
        },
        "output_sha256": _sha256(arguments.output),
    }
    print(json.dumps(summary, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
