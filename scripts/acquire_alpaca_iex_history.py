from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from us_intraday_lab.data.alpaca_iex_acquisition import (
    DEFAULT_SYMBOLS,
    ReadOnlyAlpacaIexDownloader,
    acquire_all_windows,
    audit_acquisition_environment,
    latest_completed_session,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Acquire read-only Alpaca IEX history into immutable snapshots."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--available-through", type=date.fromisoformat)
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    symbols = tuple(sorted({str(symbol).strip().upper() for symbol in args.symbols}))
    available_through = args.available_through or latest_completed_session()
    audit = audit_acquisition_environment(
        root=args.root,
        available_through=available_through,
    )
    audit["planned_symbols"] = list(symbols)
    print(json.dumps({"preflight_audit": audit}, sort_keys=True), flush=True)
    if args.audit_only:
        return
    downloader = ReadOnlyAlpacaIexDownloader.from_environment()
    manifests = acquire_all_windows(
        root=args.root,
        downloader=downloader,
        symbols=symbols,
        available_through=available_through,
    )
    for manifest in manifests:
        print(json.dumps(manifest, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
