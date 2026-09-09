from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from us_intraday_lab.data.monthly_universe import build_monthly_universe
from us_intraday_lab.data.us_market_acquisition import primary_exchange_symbols


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the point-in-time monthly universe from Alpaca SIP daily bars."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--start-month", required=True, type=date.fromisoformat)
    parser.add_argument("--end-month", required=True, type=date.fromisoformat)
    parser.add_argument("--source-start", default=date(2018, 1, 1), type=date.fromisoformat)
    parser.add_argument("--source-end", default=date(2026, 3, 31), type=date.fromisoformat)
    parser.add_argument("--source-batch-size", default=1000, type=int)
    args = parser.parse_args()
    candidate_symbols = primary_exchange_symbols(pd.read_parquet(args.assets))
    print(
        json.dumps(
            build_monthly_universe(
                root=args.root,
                start_month=args.start_month,
                end_month=args.end_month,
                source="alpaca_sip_1day_v2",
                candidate_symbols=candidate_symbols,
                source_start=args.source_start,
                source_end=args.source_end,
                source_batch_size=args.source_batch_size,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
