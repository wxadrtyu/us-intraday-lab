"""Bounded, read-only acquisition of immutable Alpaca SIP one-minute shards."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from us_intraday_lab.data.alpaca_sip_one_minute import (
    SIP_ONE_MINUTE_NAMESPACE,
    ReadOnlyAlpacaSipOneMinuteDownloader,
    acquire_sip_one_minute_shards,
    load_frozen_candidate_symbols,
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument(
        "--protocol",
        default=Path(__file__).parents[1] / "research" / "protocols" / "us_market_sip_1min_v1.json",
        type=Path,
    )
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--batch-size", default=100, type=int)
    parser.add_argument("--shard-start", required=True, type=int)
    parser.add_argument("--shard-stop", required=True, type=int)
    args = parser.parse_args(argv)

    symbols = load_frozen_candidate_symbols(assets_path=args.assets, protocol_path=args.protocol)
    records = acquire_sip_one_minute_shards(
        root=args.root,
        downloader=ReadOnlyAlpacaSipOneMinuteDownloader.from_environment(),
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
                "source_namespace": SIP_ONE_MINUTE_NAMESPACE,
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
