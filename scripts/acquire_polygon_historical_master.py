from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from us_intraday_lab.data.polygon_historical_master import (
    PolygonReferenceClient,
    acquire_activity_pages,
    build_month_snapshot,
    month_end_dates,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Acquire immutable Polygon point-in-time US-stock reference data."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--minimum-request-interval-seconds", default=13.0, type=float
    )
    args = parser.parse_args()
    if args.minimum_request_interval_seconds < 0:
        parser.error("--minimum-request-interval-seconds must be non-negative")

    client = PolygonReferenceClient.from_environment()
    for asof in month_end_dates(args.start, args.end):
        page_count = 0
        for active in (False, True):
            records = acquire_activity_pages(
                root=args.root,
                client=client,
                asof=asof,
                active=active,
                minimum_request_interval_seconds=(
                    args.minimum_request_interval_seconds
                ),
            )
            page_count += len(records)
        manifest = build_month_snapshot(args.root, asof)
        print(
            json.dumps(
                {
                    "asof": asof.isoformat(),
                    "raw_pages": page_count,
                    "rows": manifest["row_count"],
                    "active_rows": manifest["active_rows"],
                    "inactive_rows": manifest["inactive_rows"],
                    "status": "COMPLETE",
                },
                sort_keys=True,
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
