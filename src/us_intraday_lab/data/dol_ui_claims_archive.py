"""Official DOL weekly UI claims release inventory and raw PDF capture."""

import json
import os
import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urljoin, urlparse

import pandas as pd

BASE = "https://oui.doleta.gov"
ARCHIVE_URL = BASE + "/unemploy/archive.asp"
YEARS = (2021, 2022, 2023)
_PDF_PATH = re.compile(r"^/press/(20\d{2})/(\d{2})(\d{2})(\d{2})\.pdf$")
Fetch = Callable[[str, str, bytes | None], tuple[bytes, dict[str, str], int]]


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.hrefs.extend(value for key, value in attrs if key == "href" and value)


def discover_pdf_links(year_html: bytes, year: int) -> pd.DataFrame:
    """Extract exact archive-linked official PDFs with filename/date agreement."""
    if year not in YEARS:
        raise ValueError(f"year outside frozen training period: {year}")
    parser = _Links()
    parser.feed(year_html.decode("utf-8", errors="replace"))
    records: list[dict[str, object]] = []
    seen: set[date] = set()
    for href in parser.hrefs:
        url = urljoin(BASE, href)
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "oui.doleta.gov" or parsed.query:
            continue
        match = _PDF_PATH.fullmatch(parsed.path)
        if not match:
            continue
        path_year = int(match.group(1))
        if path_year != year:
            raise ValueError(f"PDF link year mismatch: {url}")
        release = date(path_year, int(match.group(2)), int(match.group(3)))
        if int(match.group(4)) != path_year % 100:
            raise ValueError(f"PDF filename year mismatch: {url}")
        if release in seen:
            raise ValueError(f"duplicate PDF release date: {release}")
        seen.add(release)
        records.append({"release_date": release, "pdf_url": url})
    if not records:
        raise ValueError(f"no official PDFs in year {year}")
    return pd.DataFrame(records).sort_values("release_date").reset_index(drop=True)


def _preserve_raw(path: Path, body: bytes) -> str:
    digest = sha256(body).hexdigest()
    if path.exists():
        if sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"source hash changed: {path}")
        return digest
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temp.write(body)
        temp_path = Path(temp.name)
    try:
        if path.exists():
            if sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError(f"source hash changed: {path}")
        else:
            os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)
    return digest


def freeze_year_indexes(fetch: Fetch, root: Path) -> dict[str, object]:
    """Freeze all three official HTML responses and 156 URLs before any PDF."""
    manifest_path = root / "source_manifest.json"
    prior = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    prior_years = {item["year"]: item for item in prior["years"]} if prior else {}
    years = []
    pdfs = []
    for year in YEARS:
        request_body = f"report=press&year={year}&submit=Submit".encode()
        body, headers, status = fetch(ARCHIVE_URL, "POST", request_body)
        if status != 200:
            raise ValueError(f"DOL year index {year} HTTP {status}")
        digest = _preserve_raw(root / "raw" / f"year_index_{year}.html", body)
        found = discover_pdf_links(body, year)
        if len(found) != 52:
            raise ValueError(f"DOL year index {year} has {len(found)} PDFs, expected 52")
        years.append({"year": year, "count": len(found), "url": ARCHIVE_URL,
                      "request_method": "POST", "request_body": request_body.decode(),
                      "sha256": digest, "byte_count": len(body), "http_status": status,
                      "headers": dict(headers),
                      "retrieved_at_utc": (
                          prior_years[year]["retrieved_at_utc"] if year in prior_years
                          else datetime.now(UTC).isoformat()
                      )})
        pdfs.extend({"release_date": row.release_date.isoformat(), "pdf_url": row.pdf_url}
                    for row in found.itertuples(index=False))
    if len(pdfs) != 156 or len({item["release_date"] for item in pdfs}) != 156:
        raise ValueError("DOL three-year PDF inventory incomplete or duplicate")
    manifest: dict[str, object] = {"years": years, "pdfs": pdfs,
                                   "status": "INDEX_FROZEN_BEFORE_PDF"}
    _preserve_raw(manifest_path, (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode())
    return manifest


def acquire_pdfs(fetch: Fetch, root: Path) -> dict[str, object]:
    """Fetch only exact links in the hash-verified, frozen source manifest."""
    manifest_path = root / "source_manifest.json"
    if not manifest_path.exists():
        raise ValueError("frozen source manifest required before PDF acquisition")
    source = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected_pdfs = []
    for year_row in source["years"]:
        year = year_row["year"]
        body = (root / "raw" / f"year_index_{year}.html").read_bytes()
        if sha256(body).hexdigest() != year_row["sha256"]:
            raise ValueError(f"year index hash mismatch: {year}")
        expected_pdfs.extend({"release_date": row.release_date.isoformat(),
                              "pdf_url": row.pdf_url}
                             for row in discover_pdf_links(body, year).itertuples(index=False))
    if expected_pdfs != source["pdfs"]:
        raise ValueError("frozen PDF URL inventory mismatch")
    pdf_manifest = root / "pdf_manifest.json"
    prior = json.loads(pdf_manifest.read_text(encoding="utf-8")) if pdf_manifest.exists() else []
    prior_by_day = {item["release_date"]: item for item in prior}
    records = []
    for item in source["pdfs"]:
        day, url = item["release_date"], item["pdf_url"]
        body, headers, status = fetch(url, "GET", None)
        if status != 200 or not body.startswith(b"%PDF-"):
            raise ValueError(f"DOL PDF invalid or HTTP {status}: {day}")
        digest = _preserve_raw(root / "raw" / "pdf" / f"{day}.pdf", body)
        records.append({"release_date": day, "url": url, "sha256": digest,
                        "byte_count": len(body), "http_status": status,
                        "headers": dict(headers), "retrieved_at_utc": (
                            prior_by_day[day]["retrieved_at_utc"] if day in prior_by_day
                            else datetime.now(UTC).isoformat()
                        )})
    _preserve_raw(pdf_manifest, (json.dumps(records, indent=2, sort_keys=True) + "\n").encode())
    return {**source, "pdf_records": records}
