"""Sequentially freeze official DOL weekly UI claims indexes, then linked PDFs."""

import argparse
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

from us_intraday_lab.data.dol_ui_claims_archive import acquire_pdfs, freeze_year_indexes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=("indexes", "pdfs"), required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    if args.stage == "pdfs" and not (args.root / "source_manifest.json").exists():
        parser.error("freeze and publish all three year indexes before PDF acquisition")

    previous_start: float | None = None

    def fetch(url: str, method: str, body: bytes | None) -> tuple[bytes, dict[str, str], int]:
        nonlocal previous_start
        if previous_start is not None:
            time.sleep(max(0.0, 1.0 - (time.monotonic() - previous_start)))
        previous_start = time.monotonic()
        request = Request(
            url, data=body, method=method,
            headers={
                "User-Agent": "us-intraday-lab-research/1.0",
                "Referer": "https://oui.doleta.gov/unemploy/claims_arch.asp",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        with urlopen(request, timeout=45) as response:
            if response.geturl() != url:
                raise ValueError(f"DOL archive URL redirected: {url} -> {response.geturl()}")
            return response.read(), {
                key: response.headers.get(key, "")
                for key in ("ETag", "Last-Modified", "Content-Type")
            }, response.status

    result = (freeze_year_indexes(fetch, args.root) if args.stage == "indexes"
              else acquire_pdfs(fetch, args.root))
    print(json.dumps({"stage": args.stage, "pdf_link_count": len(result["pdfs"]),
                      "pdfs_captured": len(result.get("pdf_records", []))}, sort_keys=True))


if __name__ == "__main__":
    main()
