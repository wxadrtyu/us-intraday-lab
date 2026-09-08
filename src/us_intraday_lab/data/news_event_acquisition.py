"""Read-only, point-in-time Alpaca News metadata acquisition.

The endpoint is queried by updated_at. Returned headline and summary text may
contain revisions, so updated_at is the only causal availability timestamp
exposed by this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from us_intraday_lab.data.alpaca_iex_acquisition import (
    API_KEY_VARIABLE,
    SECRET_KEY_VARIABLE,
)

NEWS_URL = "https://data.alpaca.markets/v1beta1/news"
TRAINING_START = date(2021, 1, 1)
TRAINING_END = date(2023, 12, 31)
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
Sleep = Callable[[float], None]
TRANSIENT_HTTP_CODES = frozenset({429, 500, 502, 503, 504})


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_updated_day(
    transport: NewsTransport,
    day: date,
    *,
    limit: int = 50,
    sleep: Sleep = time.sleep,
    max_attempts: int = 5,
    base_backoff_seconds: float = 1.0,
) -> tuple[pd.DataFrame, tuple[NewsPage, ...]]:
    """Fetch one complete UTC day, following every opaque page token."""
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("NEWS_PAGE_LIMIT_INVALID")
    if type(max_attempts) is not int or max_attempts < 1:
        raise ValueError("NEWS_RETRY_ATTEMPTS_INVALID")
    if base_backoff_seconds < 0:
        raise ValueError("NEWS_RETRY_BACKOFF_INVALID")
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
        for attempt in range(max_attempts):
            try:
                response = transport(query)
                break
            except HTTPError as error:
                if error.code not in TRANSIENT_HTTP_CODES or attempt + 1 >= max_attempts:
                    raise
                sleep(base_backoff_seconds * 2**attempt)
            except (URLError, TimeoutError):
                if attempt + 1 >= max_attempts:
                    raise
                sleep(base_backoff_seconds * 2**attempt)
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


def acquire_updated_days(
    root: Path,
    start: date,
    end: date,
    transport: NewsTransport,
) -> list[dict[str, object]]:
    """Persist complete immutable UTC-day metadata partitions for training."""
    if start > end or start < TRAINING_START or end > TRAINING_END:
        raise ValueError("ALPACA_NEWS_ACQUISITION_TRAINING_ONLY")
    output_root = root / "data/staging/alpaca_news_metadata_v1"
    records: list[dict[str, object]] = []
    current = start
    while current <= end:
        month_root = output_root / current.strftime("%Y-%m")
        month_root.mkdir(parents=True, exist_ok=True)
        parquet = month_root / f"{current.isoformat()}.parquet"
        manifest_path = month_root / f"{current.isoformat()}.json"
        if parquet.is_file() and manifest_path.is_file():
            manifest = cast(
                dict[str, object],
                json.loads(manifest_path.read_text(encoding="utf-8")),
            )
            if manifest.get("complete") is not True:
                raise ValueError(f"PARTIAL_NEWS_DAY:{current.isoformat()}")
            if manifest.get("content_sha256") != _sha256_file(parquet):
                raise ValueError(f"NEWS_DAY_HASH_MISMATCH:{current.isoformat()}")
            records.append(manifest)
            current += timedelta(days=1)
            continue
        if parquet.exists() or manifest_path.exists():
            raise ValueError(f"PARTIAL_NEWS_DAY:{current.isoformat()}")

        frame, pages = fetch_updated_day(transport, current)
        temporary_parquet = parquet.with_suffix(".tmp.parquet")
        frame.to_parquet(temporary_parquet, index=False, compression="zstd")
        content_sha256 = _sha256_file(temporary_parquet)
        manifest = {
            "schema_version": "1.0.0",
            "provider": "alpaca",
            "source_type": "historical_news_metadata",
            "utc_day": current.isoformat(),
            "available_time_field": "updated_at",
            "page_count": len(pages),
            "row_count": len(frame),
            "unique_news_ids": int(frame["news_id"].nunique()) if not frame.empty else 0,
            "symbol_links": (
                int(frame["symbols"].map(len).sum()) if not frame.empty else 0
            ),
            "rejected_rows": 0,
            "pages": list(pages),
            "content_sha256": content_sha256,
            "complete": True,
            "training_only": True,
        }
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=month_root,
            delete=False,
        ) as handle:
            json.dump(manifest, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temporary_manifest = Path(handle.name)
        temporary_parquet.replace(parquet)
        temporary_manifest.replace(manifest_path)
        records.append(manifest)
        current += timedelta(days=1)
    return records


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
