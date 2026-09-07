from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from us_intraday_lab.data.quote_feature_acquisition import (
    ReadOnlyAlpacaQuoteDownloader,
    decision_timestamp,
    latest_quote_features,
)


def test_decision_timestamp_is_end_of_completed_five_minute_bar() -> None:
    assert decision_timestamp(date(2026, 3, 2), 2) == datetime(
        2026, 3, 2, 14, 45, tzinfo=UTC
    )


def test_latest_quote_features_are_batched_causal_and_missing_is_explicit() -> None:
    cutoff = datetime(2026, 3, 2, 14, 45, tzinfo=UTC)

    class FakeDownloader(ReadOnlyAlpacaQuoteDownloader):
        def __init__(self) -> None:
            self.feed = "sip"
            self.calls: list[tuple[str, ...]] = []

        def fetch(
            self,
            *,
            symbols: tuple[str, ...],
            start: datetime,
            end: datetime,
            asof: date,
        ) -> pd.DataFrame:
            self.calls.append(symbols)
            if "AAA" not in symbols:
                return pd.DataFrame()
            return pd.DataFrame(
                {
                    "symbol": ["AAA", "AAA"],
                    "timestamp": [cutoff - timedelta(milliseconds=900), cutoff],
                    "bid_price": [99.0, 1.0],
                    "bid_size": [30.0, 1.0],
                    "bid_exchange": ["Q", "Q"],
                    "ask_price": [101.0, 2.0],
                    "ask_size": [10.0, 1.0],
                    "ask_exchange": ["N", "N"],
                    "conditions": [[], []],
                    "tape": ["C", "C"],
                }
            )

    downloader = FakeDownloader()
    result = latest_quote_features(
        downloader=downloader,
        symbols=("AAA", "BBB"),
        cutoff=cutoff,
        session_date=date(2026, 3, 2),
        sleep=lambda _: None,
        throttle_seconds=0,
    ).set_index("symbol")

    assert downloader.calls[0] == ("AAA", "BBB")
    assert all(call == ("BBB",) for call in downloader.calls[1:])
    assert bool(result.loc["AAA", "quote_available"])
    assert result.loc["AAA", "midpoint"] == 100.0
    assert result.loc["AAA", "relative_spread"] == 0.02
    assert result.loc["AAA", "size_imbalance"] == 0.5
    assert result.loc["AAA", "quote_age_ms"] == 900.0
    assert not bool(result.loc["BBB", "quote_available"])
    assert result.loc["BBB", "quotes_seen"] == 0
