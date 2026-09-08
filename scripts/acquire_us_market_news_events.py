"""Acquire immutable training-only Alpaca News metadata partitions."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from us_intraday_lab.data.news_event_acquisition import (
    AlpacaNewsHttpTransport,
    acquire_updated_days,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = _arguments()
    manifests = acquire_updated_days(
        arguments.root.resolve(),
        arguments.start,
        arguments.end,
        AlpacaNewsHttpTransport.from_environment(),
    )
    print(
        json.dumps(
            {
                "status": "COMPLETE",
                "start": arguments.start.isoformat(),
                "end": arguments.end.isoformat(),
                "days": len(manifests),
                "pages": sum(int(item["page_count"]) for item in manifests),
                "rows": sum(int(item["row_count"]) for item in manifests),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
