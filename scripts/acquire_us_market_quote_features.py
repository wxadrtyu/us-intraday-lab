from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from us_intraday_lab.data.quote_feature_acquisition import (
    ReadOnlyAlpacaQuoteDownloader,
    acquire_event_quote_features,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Acquire batched SIP/IEX quote features for the full event cross-section."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--events", required=True, type=Path)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--feed", choices=("sip", "iex"), default="sip")
    parser.add_argument("--batch-size", default=50, type=int)
    parser.add_argument("--throttle-seconds", default=0.35, type=float)
    args = parser.parse_args()
    records = acquire_event_quote_features(
        root=args.root,
        events_path=args.events,
        downloader=ReadOnlyAlpacaQuoteDownloader.from_environment(feed=args.feed),
        start=args.start,
        end=args.end,
        batch_size=args.batch_size,
        throttle_seconds=args.throttle_seconds,
    )
    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "shards": len(records),
                "requested_rows": sum(int(record["requested_rows"]) for record in records),
                "available_rows": sum(int(record["available_rows"]) for record in records),
                "missing_rows": sum(int(record["missing_rows"]) for record in records),
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
