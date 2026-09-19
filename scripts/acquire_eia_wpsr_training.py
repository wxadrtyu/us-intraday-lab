"""Fetch archived EIA WPSR release pages, then their frozen Table 4 CSV links."""

import argparse
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

from us_intraday_lab.data.eia_wpsr_archive import acquire


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("sources", "csv"), required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.stage == "csv" and not (args.root / "source_manifest.json").exists():
        parser.error("freeze the source manifest first with --stage sources")

    previous_start: float | None = None

    def fetch(url: str) -> tuple[bytes, dict[str, str], int]:
        nonlocal previous_start
        if previous_start is not None:
            time.sleep(max(0.0, 1.0 - (time.monotonic() - previous_start)))
        previous_start = time.monotonic()
        request = Request(url, headers={"User-Agent": "us-intraday-lab-research/1.0"})
        with urlopen(request, timeout=45) as response:
            return response.read(), {
                key: response.headers.get(key, "") for key in ("ETag", "Last-Modified")
            }, response.status

    result = acquire(args.root, fetch, include_csv=args.stage == "csv")
    print(json.dumps({"stage": args.stage, "release_count": len(result["releases"]),
                      "index_sha256": result["index_sha256"]}, sort_keys=True))


if __name__ == "__main__":
    main()
