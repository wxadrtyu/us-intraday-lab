"""Read-only, point-in-time Alpaca News metadata acquisition.

The endpoint is queried by updated_at. Returned headline and summary text may
contain revisions, so updated_at is the only causal availability timestamp
exposed by this module.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Protocol, cast
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from us_intraday_lab.data.alpaca_iex_acquisition import (
    API_KEY_VARIABLE,
    SECRET_KEY_VARIABLE,
)

NEWS_URL = "https://data.alpaca.markets/v1beta1/news"
CANONICAL_COLUMNS = (
    "news_id",
    "created_at",
    "available_at",
    "source",
    "symbols",
    "headline",
    "summary",
)


class NewsTransport(Protocol):
    def __call__(self, query: Mapping[str, object]) -> Mapping[str, object]: ...


type NewsPage = dict[str, object]


def _timestamp(value: object, *, reason: str) -> pd.Timestamp:
    result = pd.to_datetime(value, utc=True, errors="coerce")
    if not isinstance(result, pd.Timestamp) or pd.isna(result):
        raise ValueError(reason)
    return result


def canonicalize_article(raw: Mapping[str, object]) -> dict[str, object]:
    """Return only frozen metadata fields with conservative availability."""
    if "id" not in raw:
        raise ValueError("NEWS_ID_INVALID")
    available_at = _timestamp(raw.get("updated_at"), reason="NEWS_UPDATED_AT_INVALID")
    created_raw = raw.get("created_at")
    created_at = (
        pd.NaT
        if created_raw in (None, "")
        else _timestamp(created_raw, reason="NEWS_CREATED_AT_INVALID")
    )
    symbols_raw = raw.get("symbols", ())
    if not isinstance(symbols_raw, (list, tuple)):
        raise TypeError("NEWS_SYMBOLS_INVALID")
    return {
        "news_id": str(raw["id"]),
        "created_at": created_at,
        "available_at": available_at,
        "source": str(raw.get("source", "")),
        "symbols": tuple(sorted({str(item).upper() for item in symbols_raw if item})),
        "headline": str(raw.get("headline", "")),
        "summary": str(raw.get("summary", "")),
    }


def _jsonable(article: Mapping[str, object]) -> dict[str, object]:
    return {
        key: (
            value.isoformat()
            if isinstance(value, pd.Timestamp)
            else list(value)
            if isinstance(value, tuple)
            else value
        )
        for key, value in article.items()
    }


def _hash_json(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def fetch_updated_day(
    transport: NewsTransport, day: date, *, limit: int = 50
) -> tuple[pd.DataFrame, tuple[NewsPage, ...]]:
    """Fetch one complete UTC day, following every opaque page token."""
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("NEWS_PAGE_LIMIT_INVALID")
    start = datetime.combine(day, datetime.min.time(), UTC)
    end = start + timedelta(days=1)
    query: dict[str, object] = {
        "start": start.isoformat().replace("+00:00", "Z"),
        "end": end.isoformat().replace("+00:00", "Z"),
        "sort": "asc",
        "limit": limit,
    }
    articles_by_id: dict[str, dict[str, object]] = {}
    pages: list[NewsPage] = []
    seen_tokens: set[str] = set()
    while True:
        response = transport(query)
        raw_news = response.get("news", ())
        if not isinstance(raw_news, list):
            raise TypeError("NEWS_RESPONSE_INVALID")
        canonical_page: list[dict[str, object]] = []
        for raw in raw_news:
            if not isinstance(raw, Mapping):
                raise TypeError("NEWS_ARTICLE_INVALID")
            article = canonicalize_article(cast(Mapping[str, object], raw))
            available_at = cast(pd.Timestamp, article["available_at"])
            if not (pd.Timestamp(start) <= available_at < pd.Timestamp(end)):
                raise ValueError("NEWS_UPDATED_AT_OUTSIDE_DAY")
            news_id = cast(str, article["news_id"])
            existing = articles_by_id.get(news_id)
            if existing is not None and _jsonable(existing) != _jsonable(article):
                raise ValueError("NEWS_ID_METADATA_CONFLICT")
            articles_by_id[news_id] = article
            canonical_page.append(_jsonable(article))
        next_token_raw = response.get("next_page_token")
        next_token = "" if next_token_raw in (None, "") else str(next_token_raw)
        pages.append(
            {
                "row_count": len(canonical_page),
                "content_sha256": _hash_json(canonical_page),
                "token_sha256": _hash_json(next_token) if next_token else None,
            }
        )
        if not next_token:
            break
        if next_token in seen_tokens:
            raise ValueError("NEWS_PAGE_TOKEN_CYCLE")
        seen_tokens.add(next_token)
        query = {**query, "page_token": next_token}
    records = sorted(
        articles_by_id.values(),
        key=lambda item: (
            cast(pd.Timestamp, item["available_at"]),
            cast(str, item["news_id"]),
        ),
    )
    frame = pd.DataFrame.from_records(records, columns=CANONICAL_COLUMNS)
    if not frame.empty:
        frame["created_at"] = pd.to_datetime(frame["created_at"], utc=True)
        frame["available_at"] = pd.to_datetime(frame["available_at"], utc=True)
    return frame, tuple(pages)


class AlpacaNewsHttpTransport:
    """Credential-safe direct HTTPS transport for historical News."""

    def __init__(self, *, api_key: str, secret_key: str) -> None:
        if not api_key or not secret_key:
            raise RuntimeError(
                f"ALPACA_NEWS_CREDENTIAL_MISSING: set {API_KEY_VARIABLE} and "
                f"{SECRET_KEY_VARIABLE}"
            )
        self._headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
        }

    @classmethod
    def from_environment(
        cls, *, environ: Mapping[str, str] | None = None
    ) -> AlpacaNewsHttpTransport:
        values = os.environ if environ is None else environ
        return cls(
            api_key=values.get(API_KEY_VARIABLE, ""),
            secret_key=values.get(SECRET_KEY_VARIABLE, ""),
        )

    def __call__(self, query: Mapping[str, object]) -> Mapping[str, object]:
        request = Request(
            f"{NEWS_URL}?{urlencode(query)}",
            headers=self._headers,
            method="GET",
        )
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
        if not isinstance(payload, Mapping):
            raise TypeError("NEWS_RESPONSE_INVALID")
        return cast(Mapping[str, object], payload)
