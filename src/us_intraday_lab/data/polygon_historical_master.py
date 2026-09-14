"""Immutable Polygon point-in-time US-stock reference data.

This module uses only Polygon's historical reference-data endpoint. It has no
broker, account, position, order, submit, or cancel capability.
"""

from __future__ import annotations

import calendar
from collections.abc import Mapping
from datetime import date
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

import pandas as pd

POLYGON_API_KEY_VARIABLE = "POLYGON_API_KEY"
POLYGON_REFERENCE_NAMESPACE = "polygon_reference_tickers_v1"
POLYGON_REFERENCE_ENDPOINT = "https://api.polygon.io/v3/reference/tickers"

_REFERENCE_COLUMNS = (
    "ticker",
    "name",
    "market",
    "locale",
    "primary_exchange",
    "type",
    "active",
    "currency_name",
    "cik",
    "composite_figi",
    "share_class_figi",
    "delisted_utc",
    "last_updated_utc",
    "asof",
    "provider",
)


def month_end_dates(start: date, end: date) -> tuple[date, ...]:
    """Return one deterministic as-of date for every intersecting month."""
    if start > end:
        raise ValueError("start must not exceed end")
    values: list[date] = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        month_end = date(year, month, calendar.monthrange(year, month)[1])
        values.append(min(month_end, end))
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
    return tuple(values)


def initial_request_identity(asof: date, active: bool) -> dict[str, object]:
    """Build the complete, secret-free first-page request identity."""
    return {
        "market": "stocks",
        "locale": "us",
        "date": asof.isoformat(),
        "active": active,
        "limit": 1000,
        "sort": "ticker",
        "order": "asc",
    }


def request_url(identity: Mapping[str, object]) -> str:
    """Encode a redacted request identity as the fixed Polygon endpoint URL."""
    values = {
        key: str(value).lower() if isinstance(value, bool) else str(value)
        for key, value in identity.items()
    }
    return f"{POLYGON_REFERENCE_ENDPOINT}?{urlencode(values)}"


def validate_page_url(url: str) -> str:
    """Reject credentials and pagination redirects outside the frozen endpoint."""
    parsed = urlsplit(url)
    query_keys = {key.lower() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    if "apikey" in query_keys:
        raise ValueError("POLYGON_PAGE_URL_CONTAINS_CREDENTIAL")
    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.polygon.io"
        or parsed.path != "/v3/reference/tickers"
        or parsed.fragment
    ):
        raise ValueError("POLYGON_PAGE_URL_FORBIDDEN")
    return url


def normalize_page(
    payload: Mapping[str, object], *, asof: date, active: bool
) -> pd.DataFrame:
    """Normalize one provider page without inventing absent reference fields."""
    if payload.get("status") != "OK":
        raise ValueError("POLYGON_PAGE_STATUS_NOT_OK")
    raw_results = payload.get("results", [])
    if not isinstance(raw_results, list):
        raise TypeError("POLYGON_PAGE_RESULTS_NOT_LIST")

    rows: list[dict[str, Any]] = []
    for raw in raw_results:
        if not isinstance(raw, Mapping):
            raise TypeError("POLYGON_PAGE_RESULT_NOT_OBJECT")
        ticker = str(raw.get("ticker", "")).strip().upper()
        if not ticker:
            raise ValueError("POLYGON_TICKER_MISSING")
        if raw.get("market") != "stocks" or raw.get("locale") != "us":
            raise ValueError("POLYGON_MARKET_OR_LOCALE_MISMATCH")
        if raw.get("active") is not active:
            raise ValueError("POLYGON_ACTIVE_STATE_MISMATCH")
        row = {column: raw.get(column, pd.NA) for column in _REFERENCE_COLUMNS}
        row.update(
            {
                "ticker": ticker,
                "active": active,
                "asof": asof,
                "provider": "polygon",
            }
        )
        rows.append(row)

    result = pd.DataFrame(rows, columns=_REFERENCE_COLUMNS)
    if result.empty:
        return result
    return result.sort_values(["ticker", "active"], kind="stable").reset_index(drop=True)
