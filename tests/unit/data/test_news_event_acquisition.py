from __future__ import annotations

from collections.abc import Mapping
from datetime import date

import pandas as pd
import pytest

from us_intraday_lab.data.news_event_acquisition import fetch_updated_day


class FakeTransport:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = list(responses)
        self.calls: list[dict[str, object]] = []

    def __call__(self, query: Mapping[str, object]) -> Mapping[str, object]:
        self.calls.append(dict(query))
        return self.responses.pop(0)


def _article(*, include_updated: bool = True) -> dict[str, object]:
    result: dict[str, object] = {
        "id": 7,
        "created_at": "2022-03-14T20:00:00Z",
        "source": "wire",
        "symbols": ["AAPL"],
        "headline": "Raises guidance",
        "summary": "Outlook improves",
        "content": "forbidden",
    }
    if include_updated:
        result["updated_at"] = "2022-03-15T10:00:00Z"
    return result


def test_fetch_updated_day_pages_deduplicates_and_never_retains_content() -> None:
    transport = FakeTransport(
        [
            {"news": [_article()], "next_page_token": "opaque-secret-token"},
            {"news": [_article()], "next_page_token": None},
        ]
    )

    frame, pages = fetch_updated_day(transport, date(2022, 3, 15))

    assert frame["news_id"].tolist() == ["7"]
    assert frame["available_at"].tolist() == [pd.Timestamp("2022-03-15T10:00:00Z")]
    assert "content" not in frame.columns
    assert pages[0]["token_sha256"] != "opaque-secret-token"
    assert transport.calls[1]["page_token"] == "opaque-secret-token"


def test_fetch_updated_day_rejects_missing_updated_at() -> None:
    transport = FakeTransport([{"news": [_article(include_updated=False)]}])

    with pytest.raises(ValueError, match="NEWS_UPDATED_AT_INVALID"):
        fetch_updated_day(transport, date(2022, 3, 15))
