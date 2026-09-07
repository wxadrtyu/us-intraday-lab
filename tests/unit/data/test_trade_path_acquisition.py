from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from us_intraday_lab.data.trade_feature_acquisition import ReadOnlyAlpacaTradeDownloader
from us_intraday_lab.data.trade_path_acquisition import aggregate_trade_path_features


def test_fixed_30_second_trade_path_and_explicit_missing() -> None:
    cutoff = datetime(2026, 3, 2, 14, 45, tzinfo=UTC)

    class FakeDownloader(ReadOnlyAlpacaTradeDownloader):
        def __init__(self) -> None:
            self.feed = "sip"

        def fetch(self, *, symbols, start, end, asof):
            assert start == cutoff - timedelta(seconds=30)
            assert end == cutoff
            return pd.DataFrame({
                "symbol": ["AAA", "AAA", "AAA", "AAA"],
                "timestamp": [cutoff - timedelta(seconds=29), cutoff - timedelta(seconds=20), cutoff - timedelta(seconds=10), cutoff],
                "exchange": ["Q", "Q", "N", "N"],
                "price": [100.0, 101.0, 100.0, 500.0],
                "size": [50.0, 100.0, 150.0, 1.0],
                "id": [1, 2, 3, 4], "conditions": [[], [], [], []], "tape": ["A", "A", "A", "A"],
            })

    result = aggregate_trade_path_features(
        downloader=FakeDownloader(), symbols=("AAA", "BBB"), cutoff=cutoff,
        session_date=date(2026, 3, 2), sleep=lambda _: None,
        throttle_seconds=0,
    ).set_index("symbol")
    assert result.loc["AAA", "trades_30s"] == 3
    assert result.loc["AAA", "volume_30s"] == 300
    assert result.loc["AAA", "tick_volume_imbalance"] == -1 / 6
    assert result.loc["AAA", "back_half_activity_share"] == 0.5
    assert result.loc["AAA", "odd_lot_share"] == 1 / 6
    assert not bool(result.loc["BBB", "trade_available"])
    assert result.loc["BBB", "trades_30s"] == 0
