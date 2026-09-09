from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from us_intraday_lab.data.monthly_universe import build_monthly_universe


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the point-in-time monthly universe from Alpaca SIP daily bars."
    )
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--start-month", required=True, type=date.fromisoformat)
    parser.add_argument("--end-month", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    print(
        json.dumps(
            build_monthly_universe(
                root=args.root,
                start_month=args.start_month,
                end_month=args.end_month,
                source="alpaca_sip_1day_v1",
            ),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
