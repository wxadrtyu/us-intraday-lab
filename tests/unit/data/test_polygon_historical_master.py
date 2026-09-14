from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from us_intraday_lab.data.polygon_historical_master import (
    PolygonReferenceClient,
    acquire_activity_pages,
    initial_request_identity,
    month_end_dates,
    normalize_page,
    request_url,
    validate_page_url,
)


def _payload(
    ticker: str,
    *,
    active: bool,
    next_url: str | None = None,
    request_id: str = "request-1",
) -> bytes:
    value: dict[str, object] = {
        "status": "OK",
        "request_id": request_id,
        "results": [
            {
                "ticker": ticker,
                "name": f"{ticker} Corp",
                "market": "stocks",
                "locale": "us",
                "active": active,
            }
        ],
    }
    if next_url is not None:
        value["next_url"] = next_url
    return json.dumps(value).encode()


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


def test_client_requires_environment_key_and_uses_bearer_header_only() -> None:
    with pytest.raises(RuntimeError, match="POLYGON_API_KEY_MISSING"):
        PolygonReferenceClient.from_environment(environ={})

    seen: dict[str, object] = {}

    def transport(
        url: str, headers: Mapping[str, str]
    ) -> tuple[int, bytes, Mapping[str, str]]:
        seen.update(url=url, headers=dict(headers))
        return 200, b'{"status":"OK","results":[]}', {}

    client = PolygonReferenceClient.from_environment(
        environ={"POLYGON_API_KEY": "secret"}, transport=transport
    )
    client.get_page("https://api.polygon.io/v3/reference/tickers?limit=1000")

    assert "secret" not in str(seen["url"])
    assert seen["headers"] == {
        "Accept": "application/json",
        "Authorization": "Bearer secret",
        "User-Agent": "us-intraday-lab-polygon-master/1.0",
    }


def test_client_retries_transient_status_without_disclosing_secret() -> None:
    statuses = iter((429, 503, 200))
    delays: list[float] = []

    def transport(
        url: str, headers: Mapping[str, str]
    ) -> tuple[int, bytes, Mapping[str, str]]:
        status = next(statuses)
        body = b'{"status":"OK","results":[]}' if status == 200 else b"unavailable"
        retry_headers = {"Retry-After": "2"} if status == 429 else {}
        return status, body, retry_headers

    client = PolygonReferenceClient(
        "secret", transport=transport, sleep=delays.append
    )
    body, _ = client.get_page(
        "https://api.polygon.io/v3/reference/tickers?limit=1000"
    )

    assert json.loads(body)["status"] == "OK"
    assert delays == [2.0, 2.0]


def test_client_does_not_retry_authentication_failure() -> None:
    calls = 0

    def transport(
        url: str, headers: Mapping[str, str]
    ) -> tuple[int, bytes, Mapping[str, str]]:
        nonlocal calls
        calls += 1
        return 403, b"forbidden", {}

    client = PolygonReferenceClient("secret", transport=transport, sleep=lambda _: None)
    with pytest.raises(RuntimeError, match="POLYGON_AUTHORIZATION_FAILED"):
        client.get_page("https://api.polygon.io/v3/reference/tickers?limit=1000")
    assert calls == 1


def test_acquisition_publishes_page_pairs_and_resumes_without_network(
    tmp_path: Path,
) -> None:
    second_url = (
        "https://api.polygon.io/v3/reference/tickers?cursor=second&limit=1000"
    )
    bodies = iter(
        (
            _payload("AAA", active=True, next_url=second_url),
            _payload("BBB", active=True, request_id="request-2"),
        )
    )

    def transport(
        url: str, headers: Mapping[str, str]
    ) -> tuple[int, bytes, Mapping[str, str]]:
        return 200, next(bodies), {}

    records = acquire_activity_pages(
        root=tmp_path,
        client=PolygonReferenceClient("secret", transport=transport),
        asof=date(2018, 1, 31),
        active=True,
    )

    assert len(records) == 2
    page_root = (
        tmp_path
        / "data"
        / "staging"
        / "polygon_reference_tickers_v1"
        / "raw"
        / "asof=2018-01-31"
        / "active=true"
    )
    assert len(list(page_root.glob("page-*.json"))) == 4
    assert not list(page_root.glob("*.tmp"))
    assert "secret" not in "".join(path.read_text("utf-8") for path in page_root.iterdir())

    def fail_transport(
        url: str, headers: Mapping[str, str]
    ) -> tuple[int, bytes, Mapping[str, str]]:
        raise AssertionError("resume unexpectedly used the network")

    reused = acquire_activity_pages(
        root=tmp_path,
        client=PolygonReferenceClient("secret", transport=fail_transport),
        asof=date(2018, 1, 31),
        active=True,
    )
    assert [record["content_sha256"] for record in reused] == [
        record["content_sha256"] for record in records
    ]


def test_acquisition_rejects_partial_raw_pair(tmp_path: Path) -> None:
    client = PolygonReferenceClient(
        "secret",
        transport=lambda url, headers: (
            200,
            _payload("AAA", active=False),
            {},
        ),
    )
    acquire_activity_pages(
        root=tmp_path, client=client, asof=date(2018, 1, 31), active=False
    )
    manifest = next(
        (
            tmp_path
            / "data"
            / "staging"
            / "polygon_reference_tickers_v1"
            / "raw"
            / "asof=2018-01-31"
            / "active=false"
        ).glob("*.manifest.json")
    )
    manifest.unlink()

    with pytest.raises(ValueError, match="POLYGON_RAW_PAGE_PAIRING_FAILURE"):
        acquire_activity_pages(
            root=tmp_path, client=client, asof=date(2018, 1, 31), active=False
        )


def test_acquisition_rejects_unsafe_next_url(tmp_path: Path) -> None:
    client = PolygonReferenceClient(
        "secret",
        transport=lambda url, headers: (
            200,
            _payload(
                "AAA",
                active=True,
                next_url="https://example.com/v3/reference/tickers?cursor=stolen",
            ),
            {},
        ),
    )

    with pytest.raises(ValueError, match="POLYGON_PAGE_URL_FORBIDDEN"):
        acquire_activity_pages(
            root=tmp_path, client=client, asof=date(2018, 1, 31), active=True
        )
