from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from us_intraday_lab.data.trade_feature_acquisition import (
    ReadOnlyAlpacaTradeDownloader,
    aggregate_trade_features,
)


def test_fixed_window_trade_aggregation_and_explicit_missing() -> None:
    cutoff = datetime(2026, 3, 2, 14, 45, tzinfo=UTC)

    class FakeDownloader(ReadOnlyAlpacaTradeDownloader):
        def __init__(self) -> None:
            self.feed = "sip"

        def fetch(self, *, symbols, start, end, asof):
            assert start == cutoff - timedelta(seconds=1)
            return pd.DataFrame({
                "symbol": ["AAA", "AAA", "AAA"],
                "timestamp": [cutoff - timedelta(milliseconds=900), cutoff - timedelta(milliseconds=500), cutoff],
                "exchange": ["Q", "N", "Q"],
                "price": [99.9, 100.1, 200.0],
                "size": [50.0, 150.0, 1.0],
                "id": [1, 2, 3], "conditions": [[], [], []], "tape": ["A", "A", "A"],
            })

    result = aggregate_trade_features(
        downloader=FakeDownloader(), symbols=("AAA", "BBB"), cutoff=cutoff,
        session_date=date(2026, 3, 2), midpoint_by_symbol={"AAA": 100.0, "BBB": 20.0},
        sleep=lambda _: None, throttle_seconds=0,
    ).set_index("symbol")
    assert result.loc["AAA", "trades_1s"] == 2
    assert result.loc["AAA", "volume_1s"] == 200
    assert result.loc["AAA", "trade_location_volume_imbalance"] == 0.5
    assert result.loc["AAA", "odd_lot_share"] == 0.25
    assert not bool(result.loc["BBB", "trade_available"])
    assert result.loc["BBB", "trades_1s"] == 0


def test_fully_empty_trade_window_is_retained_as_missing() -> None:
    cutoff = datetime(2026, 3, 2, 14, 45, tzinfo=UTC)

    class EmptyDownloader(ReadOnlyAlpacaTradeDownloader):
        def __init__(self) -> None:
            self.feed = "sip"

        def fetch(self, *, symbols, start, end, asof):
            return pd.DataFrame()

    result = aggregate_trade_features(
        downloader=EmptyDownloader(), symbols=("AAA",), cutoff=cutoff,
        session_date=date(2026, 3, 2), midpoint_by_symbol={"AAA": 100.0},
        sleep=lambda _: None, throttle_seconds=0,
    )
    assert result["trade_available"].tolist() == [False]
    assert result["trades_1s"].tolist() == [0]
