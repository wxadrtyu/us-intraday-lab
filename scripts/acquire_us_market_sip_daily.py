from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from us_intraday_lab.data.alpaca_sip_daily import (
    SIP_DAILY_NAMESPACE,
    ReadOnlyAlpacaSipDailyDownloader,
    acquire_sip_daily_shards,
)
from us_intraday_lab.data.us_market_acquisition import primary_exchange_symbols


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Acquire immutable consolidated Alpaca SIP daily market-data shards."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--batch-size", default=100, type=int)
    args = parser.parse_args()

    assets = pd.read_parquet(args.assets)
    symbols = primary_exchange_symbols(assets)
    records = acquire_sip_daily_shards(
        root=args.root,
        downloader=ReadOnlyAlpacaSipDailyDownloader.from_environment(),
        symbols=symbols,
        start=args.start,
        end=args.end,
        batch_size=args.batch_size,
    )
    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "source_namespace": SIP_DAILY_NAMESPACE,
                "symbols": len(symbols),
                "shards": len(records),
                "rows": sum(int(record["row_count"]) for record in records),
                "provider_rejected_symbols": sum(
                    len(record["provider_rejected_symbols"]) for record in records
                ),
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
