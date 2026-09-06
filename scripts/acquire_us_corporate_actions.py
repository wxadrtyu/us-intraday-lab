from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from us_intraday_lab.data.corporate_actions import (
    fetch_corporate_actions,
    publish_corporate_actions,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire immutable US corporate actions.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--start", default=date(2018, 10, 1), type=date.fromisoformat)
    parser.add_argument("--end", default=date(2026, 9, 4), type=date.fromisoformat)
    args = parser.parse_args()
    rows, pages = fetch_corporate_actions(start=args.start, end=args.end)
    print(
        json.dumps(
            publish_corporate_actions(
                rows, root=args.root, start=args.start, end=args.end, pages=pages
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
