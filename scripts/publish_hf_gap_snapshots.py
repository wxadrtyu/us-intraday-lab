from __future__ import annotations

import argparse
import json
from pathlib import Path

from us_intraday_lab.data.hf_gap_snapshot import publish_hf_gap_snapshot


def _months(start: str, end: str) -> tuple[str, ...]:
    first_year, first_month = map(int, start.split("-"))
    last_year, last_month = map(int, end.split("-"))
    result: list[str] = []
    year, month = first_year, first_month
    while (year, month) <= (last_year, last_month):
        result.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return tuple(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--repo", default=Path.cwd(), type=Path)
    args = parser.parse_args()
    windows = (
        ("late-2018-and-2019-transition", _months("2018-10", "2019-12")),
        ("covid-crash-rebound-2020", _months("2020-01", "2020-12")),
    )
    for label, months in windows:
        manifest = publish_hf_gap_snapshot(
            repo=args.repo, root=args.root, label=label, months=months
        )
        print(json.dumps(manifest, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
