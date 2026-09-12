from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from us_intraday_lab.data.alpaca_sip_five_minute import (
    SIP_FIVE_MINUTE_NAMESPACE,
    ReadOnlyAlpacaSipFiveMinuteDownloader,
    acquire_sip_five_minute_shards,
    load_frozen_candidate_symbols,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Acquire immutable Alpaca SIP five-minute full-market shards."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument(
        "--protocol",
        default=Path(__file__).parents[1]
        / "research"
        / "protocols"
        / "us_market_sip_5min_v1.json",
        type=Path,
    )
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--batch-size", default=100, type=int)
    parser.add_argument("--shard-start", default=0, type=int)
    parser.add_argument("--shard-stop", type=int)
    args = parser.parse_args()

    symbols = load_frozen_candidate_symbols(
        assets_path=args.assets, protocol_path=args.protocol
    )
    records = acquire_sip_five_minute_shards(
        root=args.root,
        downloader=ReadOnlyAlpacaSipFiveMinuteDownloader.from_environment(),
        symbols=symbols,
        start=args.start,
        end=args.end,
        batch_size=args.batch_size,
        shard_start=args.shard_start,
        shard_stop=args.shard_stop,
    )
    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "source_namespace": SIP_FIVE_MINUTE_NAMESPACE,
                "candidate_symbols": len(symbols),
                "selected_shards": len(records),
                "rows": sum(int(record["row_count"]) for record in records),
                "provider_rejected_symbols": sum(
                    len(record["provider_rejected_symbols"]) for record in records
                ),
                "shard_start": args.shard_start,
                "shard_stop": args.shard_stop,
            },
            sort_keys=True,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
