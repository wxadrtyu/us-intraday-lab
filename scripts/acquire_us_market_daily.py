from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from us_intraday_lab.data.us_market_acquisition import (
    ReadOnlyDailyBarDownloader,
    acquire_daily_shards,
    fetch_asset_catalog,
    normalize_asset_catalog,
    primary_exchange_symbols,
    publish_asset_catalog,
    unqueryable_primary_symbols,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Acquire an immutable US-equity master and full-market IEX daily shards."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--start", default=date(2018, 10, 1), type=date.fromisoformat)
    parser.add_argument("--end", default=date(2026, 9, 4), type=date.fromisoformat)
    parser.add_argument("--batch-size", default=100, type=int)
    args = parser.parse_args()

    assets = normalize_asset_catalog(fetch_asset_catalog())
    catalog = publish_asset_catalog(assets, root=args.root)
    symbols = primary_exchange_symbols(assets)
    unqueryable = unqueryable_primary_symbols(assets)
    print(
        json.dumps(
            {
                "asset_catalog": catalog,
                "planned_unique_symbols": len(symbols),
                "unqueryable_asset_identifiers_retained_in_catalog": len(unqueryable),
            },
            sort_keys=True,
        ),
        flush=True,
    )
    records = acquire_daily_shards(
        root=args.root,
        downloader=ReadOnlyDailyBarDownloader.from_environment(),
        symbols=symbols,
        start=args.start,
        end=args.end,
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
