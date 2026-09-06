from __future__ import annotations

import argparse
import json
from pathlib import Path

from us_intraday_lab.data.alpaca_iex_acquisition import ReadOnlyAlpacaIexDownloader
from us_intraday_lab.data.market_minute_acquisition import acquire_eligible_minutes


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Acquire all point-in-time eligible US stock minute bars."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--decisions", required=True, type=Path)
    parser.add_argument("--batch-size", default=25, type=int)
    args = parser.parse_args()
    records = acquire_eligible_minutes(
        root=args.root,
        decisions_path=args.decisions,
        downloader=ReadOnlyAlpacaIexDownloader.from_environment(),
        batch_size=args.batch_size,
    )
    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "shards": len(records),
                "rows": sum(int(record["row_count"]) for record in records),
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
