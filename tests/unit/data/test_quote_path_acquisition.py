from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from us_intraday_lab.data.quote_feature_acquisition import ReadOnlyAlpacaQuoteDownloader
from us_intraday_lab.data.quote_path_acquisition import aggregate_quote_path_features


def test_fixed_five_second_quote_path_and_explicit_missing() -> None:
    cutoff = datetime(2026, 3, 2, 14, 45, tzinfo=UTC)

    class FakeDownloader(ReadOnlyAlpacaQuoteDownloader):
        def __init__(self) -> None:
            self.feed = "sip"

        def fetch(self, *, symbols, start, end, asof):
            assert symbols == ("AAA", "BBB")
            assert start == cutoff - timedelta(seconds=5)
            assert end == cutoff
            assert asof == date(2026, 3, 2)
            return pd.DataFrame({
                "symbol": ["AAA", "AAA", "AAA", "AAA"],
                "timestamp": [cutoff - timedelta(seconds=4), cutoff - timedelta(seconds=3), cutoff - timedelta(seconds=1), cutoff],
                "bid_price": [99.0, 100.0, 101.0, 999.0],
                "ask_price": [101.0, 102.0, 103.0, 1000.0],
                "bid_size": [100.0, 200.0, 300.0, 1.0],
                "ask_size": [100.0, 100.0, 100.0, 1.0],
                "bid_exchange": ["Q"] * 4, "ask_exchange": ["N"] * 4,
                "conditions": [[], [], [], []], "tape": ["A"] * 4,
            })

    result = aggregate_quote_path_features(
        downloader=FakeDownloader(), symbols=("AAA", "BBB"), cutoff=cutoff,
        session_date=date(2026, 3, 2), sleep=lambda _: None, throttle_seconds=0,
    ).set_index("symbol")
    assert result.loc["AAA", "quotes_5s"] == 3
    assert result.loc["AAA", "midpoint_return"] == pytest.approx(0.02)
    assert result.loc["AAA", "size_imbalance_change"] == pytest.approx(0.5)
    assert result.loc["AAA", "back_half_update_share"] == pytest.approx(1 / 3)
    assert result.loc["AAA", "last_quote_age_ms"] == pytest.approx(1000.0)
    assert not bool(result.loc["BBB", "quote_available"])
    assert result.loc["BBB", "quotes_5s"] == 0
