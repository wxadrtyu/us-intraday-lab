from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from us_intraday_lab.data.monthly_universe import build_monthly_universe


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a point-in-time monthly US stock universe.")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--start-month", default=date(2021, 1, 1), type=date.fromisoformat)
    parser.add_argument("--end-month", default=date(2026, 9, 1), type=date.fromisoformat)
    args = parser.parse_args()
    print(
        json.dumps(
            build_monthly_universe(
                root=args.root,
                start_month=args.start_month,
                end_month=args.end_month,
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
