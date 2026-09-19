"""First-page-only extraction of dated DOL unemployment-claims releases."""

import io
import re
from datetime import date
from hashlib import sha256
from time import strptime

from pypdf import PdfReader

_DATE = re.compile(
    r"(?:for release|embargoed until)\s+8:30\s*a\.m\.\s*\((?:ET|Eastern)\)\s+"
    r"(?:Monday|Tuesday|Wednesday|Thursday|Friday),?\s+"
    r"([A-Z][a-z]+\s+\d{1,2},\s+20\d{2})",
    flags=re.IGNORECASE,
)
_INITIAL = re.compile(
    r"advance figure for seasonally adjusted initial claims\s+was\s+([\d,]+)",
    flags=re.IGNORECASE,
)
_INSURED = re.compile(
    r"advance number for seasonally adjusted insured unemployment\b"
    r"[^.]{0,250}?\bwas\s+([\d,]+)",
    flags=re.IGNORECASE,
)


def _one_value(pattern: re.Pattern[str], text: str, field: str) -> int:
    matches = pattern.findall(text)
    if len(matches) != 1:
        raise ValueError(f"missing or ambiguous {field}: {len(matches)} matches")
    return int(matches[0].replace(",", ""))


def parse_first_page_text(text: str, expected_date: date) -> dict[str, object]:
    """Parse only the explicit release date and two advance seasonally adjusted values."""
    normalized = " ".join(text.split())
    release_dates = _DATE.findall(normalized)
    if len(release_dates) != 1:
        raise ValueError(f"expected exactly one explicit 8:30 ET release date, got {len(release_dates)}")
    parsed_date = strptime(release_dates[0], "%B %d, %Y")
    released = date(parsed_date.tm_year, parsed_date.tm_mon, parsed_date.tm_mday)
    if released != expected_date:
        raise ValueError(f"release date mismatch: {released} vs {expected_date}")
    return {
        "release_date": released,
        "release_time_et": "08:30",
        "initial_sa": _one_value(_INITIAL, normalized, "initial claims"),
        "insured_sa": _one_value(_INSURED, normalized, "insured unemployment"),
        "first_page_text_sha256": sha256(normalized.encode("utf-8")).hexdigest(),
    }


def extract_first_page(pdf: bytes, expected_date: date) -> dict[str, object]:
    """Read the first PDF page only; later revision tables cannot enter the signal."""
    if not pdf.startswith(b"%PDF-"):
        raise ValueError("not a PDF")
    reader = PdfReader(io.BytesIO(pdf))
    if not reader.pages:
        raise ValueError("PDF has no pages")
    text = reader.pages[0].extract_text()
    if not text:
        raise ValueError("first PDF page has no extractable text")
    return parse_first_page_text(text, expected_date)
