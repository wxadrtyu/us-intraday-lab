from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from us_intraday_lab.data.trade_feature_acquisition import (
    ReadOnlyAlpacaTradeDownloader,
    acquire_event_trade_features,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--quotes", required=True, type=Path)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--batch-size", default=50, type=int)
    parser.add_argument("--throttle-seconds", default=0.35, type=float)
    args = parser.parse_args()
    records = acquire_event_trade_features(
        root=args.root, events_path=args.events, quotes_path=args.quotes,
        downloader=ReadOnlyAlpacaTradeDownloader.from_environment(),
        start=args.start, end=args.end, batch_size=args.batch_size,
        throttle_seconds=args.throttle_seconds,
    )
    print(json.dumps({
        "status": "COMPLETE", "shards": len(records),
        "requested_rows": sum(int(item["requested_rows"]) for item in records),
        "available_rows": sum(int(item["available_rows"]) for item in records),
        "missing_rows": sum(int(item["missing_rows"]) for item in records),
    }, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
