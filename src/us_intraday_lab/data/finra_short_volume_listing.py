"""Official FINRA monthly-index evidence for historical file availability."""

from __future__ import annotations

import hashlib
import re
import time
from collections.abc import Callable
from datetime import date, datetime
from datetime import time as wall_time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import pandas as pd

INDEX_URL = (
    "https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data/"
    "daily-short-sale-volume-files"
)
YEAR_FILTER_VALUES = {2021: "5", 2022: "4", 2023: "3"}
FetchMonth = Callable[[int, int], bytes]
_SECTION = re.compile(
    rb"FINRA Consolidated NMS(?P<body>.*?)(?:FINRA/NASDAQ TRF Chicago|</main>)",
    re.IGNORECASE | re.DOTALL,
)
_LIST_ITEM = re.compile(
    rb"<li\b[^>]*>(?P<body>.*?CNMSshvol(?P<date>\d{8})\.txt.*?)</li>",
    re.IGNORECASE | re.DOTALL,
)


def parse_month_listing(body: bytes) -> dict[date, bool]:
    """Return exact Consolidated NMS dates and whether the index says Updated."""
    section = _SECTION.search(body)
    if section is None:
        raise ValueError("FINRA_LISTING_NMS_SECTION_MISSING")
    result: dict[date, bool] = {}
    for match in _LIST_ITEM.finditer(section.group("body")):
        raw_date = match.group("date").decode()
        trade_date = date(int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8]))
        updated = b"updated" in match.group("body").lower()
        if trade_date in result:
            updated = True
        result[trade_date] = updated
    if not result:
        raise ValueError("FINRA_LISTING_NMS_FILES_MISSING")
    return result


def build_listing_audit(
    manifests: pd.DataFrame, fetch_month: FetchMonth
) -> pd.DataFrame:
    """Derive conservative availability from CDN and official index evidence."""
    required = {"trade_date", "last_modified"}
    if missing := required.difference(manifests.columns):
        raise ValueError(f"FINRA_LISTING_MANIFEST_COLUMNS_MISSING:{sorted(missing)}")
    frame = manifests.loc[:, ["trade_date", "last_modified"]].copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.date
    frame["last_modified"] = pd.to_datetime(frame["last_modified"], utc=True)
    if frame["trade_date"].duplicated().any():
        raise ValueError("FINRA_LISTING_MANIFEST_DATE_DUPLICATE")
    late = frame["last_modified"].dt.date > frame["trade_date"]
    snapshots: dict[tuple[int, int], tuple[dict[date, bool], str]] = {}
    for trade_date in sorted(frame.loc[late, "trade_date"]):
        key = (trade_date.year, trade_date.month)
        if key not in snapshots:
            body = fetch_month(*key)
            snapshots[key] = (parse_month_listing(body), hashlib.sha256(body).hexdigest())
    records: list[dict[str, object]] = []
    eastern = ZoneInfo("America/New_York")
    for row in frame.itertuples(index=False):
        trade_date = row.trade_date
        last_modified = row.last_modified
        if last_modified.date() <= trade_date:
            evidence = "SAME_DAY_LAST_MODIFIED"
            causal_available_at = last_modified
            index_sha256 = None
        else:
            listing, index_sha256 = snapshots[(trade_date.year, trade_date.month)]
            if trade_date in listing and not listing[trade_date]:
                evidence = "ORIGINAL_OFFICIAL_INDEX"
                causal_available_at = pd.Timestamp(
                    datetime.combine(trade_date, wall_time(18, 0), eastern)
                ).tz_convert("UTC")
            elif listing.get(trade_date) is True:
                evidence = "UPDATED_OFFICIAL_INDEX"
                causal_available_at = last_modified
            else:
                evidence = "NOT_LISTED_OFFICIAL_INDEX"
                causal_available_at = last_modified
        records.append(
            {
                "trade_date": trade_date,
                "last_modified": last_modified,
                "causal_available_at": causal_available_at,
                "availability_evidence": evidence,
                "index_sha256": index_sha256,
            }
        )
    return pd.DataFrame.from_records(records).sort_values("trade_date").reset_index(drop=True)


class FinraMonthlyListingHttpTransport:
    """Low-rate official-index transport for the frozen 2021-2023 audit."""

    def __init__(self, *, delay_seconds: float = 5.0) -> None:
        self._delay_seconds = delay_seconds
        self._called = False

    def __call__(self, year: int, month: int) -> bytes:
        if year not in YEAR_FILTER_VALUES or not 1 <= month <= 12:
            raise ValueError("FINRA_LISTING_TRAINING_MONTH_INVALID")
        if self._called:
            time.sleep(self._delay_seconds)
        self._called = True
        url = f"{INDEX_URL}?{urlencode({'custom_month[month]': f'{month:02d}', 'custom_year[year]': YEAR_FILTER_VALUES[year]})}"
        request = Request(url, headers={"User-Agent": "us-intraday-lab-research/1.0"})
        for attempt in range(5):
            try:
                with urlopen(request, timeout=30) as response:
                    return response.read()
            except HTTPError as error:
                if error.code != 429 or attempt == 4:
                    raise
                time.sleep(15.0 * (attempt + 1))
            except (URLError, TimeoutError):
                if attempt == 4:
                    raise
                time.sleep(5.0 * (attempt + 1))
        raise RuntimeError("FINRA_LISTING_FETCH_UNREACHABLE")
