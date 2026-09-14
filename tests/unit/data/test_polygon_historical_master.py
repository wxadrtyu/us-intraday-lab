from __future__ import annotations

import json
from datetime import date

import pandas as pd
import pytest

from us_intraday_lab.data.polygon_historical_master import (
    initial_request_identity,
    month_end_dates,
    normalize_page,
    request_url,
    validate_page_url,
)


def test_month_ends_are_complete_and_clamped() -> None:
    assert month_end_dates(date(2018, 1, 1), date(2018, 3, 15)) == (
        date(2018, 1, 31),
        date(2018, 2, 28),
        date(2018, 3, 15),
    )


def test_month_ends_reject_reversed_range() -> None:
    with pytest.raises(ValueError, match="start must not exceed end"):
        month_end_dates(date(2018, 2, 1), date(2018, 1, 31))


def test_request_identity_is_deterministic_and_secret_free() -> None:
    identity = initial_request_identity(date(2018, 1, 31), False)

    assert identity == {
        "market": "stocks",
        "locale": "us",
        "date": "2018-01-31",
        "active": False,
        "limit": 1000,
        "sort": "ticker",
        "order": "asc",
    }
    assert "api" not in json.dumps(identity).lower()
    assert request_url(identity).startswith(
        "https://api.polygon.io/v3/reference/tickers?"
    )


@pytest.mark.parametrize(
    "url, reason",
    [
        (
            "https://example.com/v3/reference/tickers",
            "POLYGON_PAGE_URL_FORBIDDEN",
        ),
        (
            "http://api.polygon.io/v3/reference/tickers",
            "POLYGON_PAGE_URL_FORBIDDEN",
        ),
        (
            "https://api.polygon.io/v2/reference/tickers",
            "POLYGON_PAGE_URL_FORBIDDEN",
        ),
        (
            "https://api.polygon.io/v3/reference/tickers?apiKey=x",
            "POLYGON_PAGE_URL_CONTAINS_CREDENTIAL",
        ),
    ],
)
def test_page_url_rejects_unsafe_destinations(url: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        validate_page_url(url)


def test_normalize_preserves_nulls_and_provenance() -> None:
    frame = normalize_page(
        {
            "status": "OK",
            "results": [
                {
                    "ticker": "abc",
                    "name": "ABC Corp",
                    "market": "stocks",
                    "locale": "us",
                    "active": False,
                }
            ],
        },
        asof=date(2018, 1, 31),
        active=False,
    )

    assert frame.loc[0, "ticker"] == "ABC"
    assert pd.isna(frame.loc[0, "primary_exchange"])
    assert frame.loc[0, "asof"] == date(2018, 1, 31)
    assert frame.loc[0, "provider"] == "polygon"


def test_normalize_rejects_provider_or_state_mismatch() -> None:
    with pytest.raises(ValueError, match="POLYGON_ACTIVE_STATE_MISMATCH"):
        normalize_page(
            {
                "status": "OK",
                "results": [
                    {
                        "ticker": "ABC",
                        "market": "stocks",
                        "locale": "us",
                        "active": True,
                    }
                ],
            },
            asof=date(2018, 1, 31),
            active=False,
        )

    with pytest.raises(ValueError, match="POLYGON_PAGE_STATUS_NOT_OK"):
        normalize_page(
            {"status": "ERROR", "results": []},
            asof=date(2018, 1, 31),
            active=False,
        )
