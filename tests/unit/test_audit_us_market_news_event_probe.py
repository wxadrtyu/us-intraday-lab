from __future__ import annotations

from collections.abc import Mapping
from datetime import date

from scripts.audit_us_market_news_event_probe import audit_probe
from us_intraday_lab.data.news_event_acquisition import acquire_updated_days


class OnePageTransport:
    def __call__(self, query: Mapping[str, object]) -> Mapping[str, object]:
        return {
            "news": [
                {
                    "id": 11,
                    "created_at": "2022-03-15T09:00:00Z",
                    "updated_at": "2022-03-15T10:00:00Z",
                    "source": "wire",
                    "symbols": ["AAPL", "MSFT"],
                    "headline": "Raises guidance",
                    "summary": "Outlook improves",
                }
            ],
            "next_page_token": None,
        }


def test_probe_audit_requires_complete_pages_and_has_no_strategy_metrics(
    tmp_path,
) -> None:
    acquire_updated_days(
        tmp_path,
        date(2022, 3, 15),
        date(2022, 3, 15),
        OnePageTransport(),
    )

    result = audit_probe(
        root=tmp_path,
        start=date(2022, 3, 15),
        end=date(2022, 3, 15),
    )

    assert result["available_time_field"] == "updated_at"
    assert result["training_only"] is True
    assert result["partial_days"] == 0
    assert result["estimated_full_calls"] > 0
    assert result["unique_news_ids"] == 1
    assert result["symbol_links"] == 2
    assert "annualized_return" not in result
    assert "information_ratio" not in result
