"""Fail-closed parser for dated EIA WPSR Table 4 archive releases."""

import csv
import json
import os
import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from hashlib import sha256
from html.parser import HTMLParser
from io import StringIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urljoin, urlparse

import pandas as pd

ARCHIVE = "https://www.eia.gov/petroleum/supply/weekly/archive/"
ROWS = (
    "Commercial (Excluding SPR)",
    "Total Motor Gasoline",
    "Distillate Fuel Oil",
    "Total Stocks (Excluding SPR)",
)
_ISSUE = re.compile(
    r"^/petroleum/supply/weekly/archive/(20\d{2})/"
    r"(20\d{2}_\d{2}_\d{2})/wpsr_\2\.php$"
)


class _LinksAndText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[str] = []
        self.words: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href" and value)

    def handle_data(self, data: str) -> None:
        self.words.append(data)


def _html(body: bytes) -> _LinksAndText:
    parser = _LinksAndText()
    parser.feed(body.decode("utf-8", errors="replace"))
    return parser


def discover_releases(index_html: bytes) -> pd.DataFrame:
    """Return the exact 2021-23 archive issue links, rejecting duplicates."""
    found: list[dict[str, object]] = []
    dates: set[date] = set()
    for href in _html(index_html).links:
        url = urljoin(ARCHIVE, href)
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "www.eia.gov" or parsed.query:
            continue
        match = _ISSUE.fullmatch(parsed.path)
        if not match or int(match.group(1)) not in (2021, 2022, 2023):
            continue
        release = date.fromisoformat(match.group(2).replace("_", "-"))
        if release.year != int(match.group(1)):
            raise ValueError("issue directory/date mismatch")
        if release in dates:
            raise ValueError(f"duplicate issue date: {release}")
        dates.add(release)
        found.append({"release_date": release, "page_url": url})
    if not found:
        raise ValueError("no official 2021-2023 issue links")
    return pd.DataFrame(found).sort_values("release_date").reset_index(drop=True)


def discover_table4(page_html: bytes, page_url: str) -> str:
    """Validate stated issue date and exactly one same-issue Table 4 link."""
    parsed = urlparse(page_url)
    match = _ISSUE.fullmatch(parsed.path)
    if parsed.scheme != "https" or parsed.netloc != "www.eia.gov" or not match:
        raise ValueError("not an official issue page")
    release = date.fromisoformat(match.group(2).replace("_", "-"))
    page = _html(page_html)
    text = " ".join(page.words)
    stated = re.search(r"Release Date:\s*([A-Za-z]+\s+\d{1,2},\s+20\d{2})", text)
    if not stated or datetime.strptime(stated.group(1), "%B %d, %Y").replace(tzinfo=UTC).date() != release:
        raise ValueError("release date mismatch or absent")
    candidate = [urljoin(page_url, href) for href in page.links if href.lower().endswith("table4.csv")]
    if len(candidate) != 1:
        raise ValueError("expected exactly one Table 4 CSV link")
    expected = page_url.rsplit("/", 1)[0] + "/csv/table4.csv"
    if candidate[0] != expected:
        raise ValueError("Table 4 not in same-issue archive directory")
    return expected


def parse_table4(body: bytes, release_date: date) -> pd.DataFrame:
    """Extract only four exact current-vs-prior-week Difference values."""
    try:
        reader = csv.DictReader(StringIO(body.decode("utf-8-sig"), newline=""), strict=True)
        headers = reader.fieldnames or []
        if headers.count("Difference") != 1 or headers.count("STUB_1") != 1:
            raise ValueError("unambiguous Difference/STUB_1 headers required")
        selected: dict[str, float] = {}
        for row in reader:
            name = row["STUB_1"]
            if name not in ROWS:
                continue
            if name in selected:
                raise ValueError(f"duplicate row: {name}")
            raw = row["Difference"]
            if raw is None or not re.fullmatch(r"-?\d[\d,]*(?:\.\d+)?", raw.strip()):
                raise ValueError(f"invalid Difference for row {name}")
            selected[name] = float(raw.replace(",", ""))
    except (UnicodeError, csv.Error, KeyError) as exc:
        raise ValueError("invalid Table 4 CSV schema") from exc
    if set(selected) != set(ROWS):
        raise ValueError(f"missing exact Table 4 row: {set(ROWS) - set(selected)}")
    return pd.DataFrame(
        {"release_date": [release_date] * len(ROWS), "row_name": ROWS,
         "difference": [selected[name] for name in ROWS]}
    )


def preserve_raw(target: Path, body: bytes) -> str:
    """Write raw bytes once; identical re-fetch is safe, changed bytes fail closed."""
    digest = sha256(body).hexdigest()
    if target.exists():
        if sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError(f"source hash changed: {target}")
        return digest
    target.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=target.parent, delete=False) as temp:
        temp.write(body)
        temp_path = Path(temp.name)
    try:
        if target.exists():
            if sha256(target.read_bytes()).hexdigest() != digest:
                raise ValueError(f"source hash changed: {target}")
        else:
            os.replace(temp_path, target)
    finally:
        temp_path.unlink(missing_ok=True)
    return digest


Fetch = Callable[[str], tuple[bytes, dict[str, str], int]]


def acquire(root: Path, fetch: Fetch, *, include_csv: bool = False) -> dict[str, object]:
    """Freeze the dated issue inventory before optionally retrieving its CSVs."""
    manifest_path = root / "source_manifest.json"
    prior = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    index_body, index_headers, index_status = fetch(ARCHIVE)
    if index_status != 200:
        raise ValueError(f"archive index HTTP {index_status}")
    index_hash = preserve_raw(root / "raw" / "archive_index.html", index_body)
    releases = discover_releases(index_body)
    records: list[dict[str, object]] = []
    prior_records = {item["release_date"]: item for item in prior["releases"]} if prior else {}
    for row in releases.itertuples(index=False):
        body, headers, status = fetch(row.page_url)
        if status != 200:
            raise ValueError(f"issue {row.release_date} HTTP {status}")
        day = row.release_date.isoformat()
        page_hash = preserve_raw(root / "raw" / "pages" / f"{day}.html", body)
        records.append({
            "release_date": day,
            "page_url": row.page_url,
            "page_sha256": page_hash,
            "page_headers": dict(headers),
            "page_http_status": status,
            "page_byte_count": len(body),
            "page_retrieved_at_utc": (
                prior_records[day]["page_retrieved_at_utc"] if day in prior_records
                else datetime.now(UTC).isoformat()
            ),
            "csv_url": discover_table4(body, row.page_url),
        })
    result: dict[str, object] = {
        "index_url": ARCHIVE,
        "index_sha256": index_hash,
        "index_headers": dict(index_headers),
        "index_http_status": index_status,
        "index_byte_count": len(index_body),
        "retrieved_at_utc": prior["retrieved_at_utc"] if prior else datetime.now(UTC).isoformat(),
        "releases": records,
    }
    preserve_raw(manifest_path, (json.dumps(result, indent=2, sort_keys=True) + "\n").encode())
    if not include_csv:
        return result
    csv_records = []
    csv_manifest = root / "csv_manifest.json"
    prior_csv = {
        item["release_date"]: item
        for item in json.loads(csv_manifest.read_text(encoding="utf-8"))
    } if csv_manifest.exists() else {}
    for record in records:
        day, url = str(record["release_date"]), str(record["csv_url"])
        body, headers, status = fetch(url)
        if status != 200:
            raise ValueError(f"Table 4 {day} HTTP {status}")
        digest = preserve_raw(root / "raw" / "csv" / f"{day}.csv", body)
        parse_table4(body, date.fromisoformat(day))
        csv_records.append({"release_date": day, "url": url, "sha256": digest,
                            "byte_count": len(body), "http_status": status, "headers": dict(headers),
                            "retrieved_at_utc": (
                                prior_csv[day]["retrieved_at_utc"] if day in prior_csv
                                else datetime.now(UTC).isoformat()
                            )})
    preserve_raw(csv_manifest, (json.dumps(csv_records, indent=2, sort_keys=True) + "\n").encode())
    return {**result, "csv_records": csv_records}
