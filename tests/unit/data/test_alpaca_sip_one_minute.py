from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from us_intraday_lab.data.alpaca_sip_one_minute import (
    SIP_ONE_MINUTE_NAMESPACE,
    ReadOnlyAlpacaSipOneMinuteDownloader,
    partition_specs,
)


class FakeHistoricalClient:
    def __init__(self) -> None:
        self.request: object | None = None

    def get_stock_bars(self, request: object) -> object:
        self.request = request
        frame = pd.DataFrame(
            {
                "symbol": ["aaa"],
                "timestamp": [pd.Timestamp("2025-01-02T14:30:00Z")],
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.5],
                "volume": [1000.0],
                "trade_count": [20.0],
                "vwap": [100.2],
            }
        )
        return SimpleNamespace(df=frame)


def test_downloader_requests_read_only_sip_one_minute_with_asof() -> None:
    client = FakeHistoricalClient()
    bars = ReadOnlyAlpacaSipOneMinuteDownloader(client).fetch(
        symbols=("AAA",),
        start=date(2025, 1, 2),
        end=date(2025, 1, 2),
        asof=date(2025, 1, 31),
    )
    request = client.request
    assert request is not None
    assert request.timeframe.amount == 1  # type: ignore[attr-defined]
    assert request.timeframe.unit.value == "Min"  # type: ignore[attr-defined]
    assert request.feed.value == "sip"  # type: ignore[attr-defined]
    assert request.adjustment.value == "split"  # type: ignore[attr-defined]
    assert request.asof == "2025-01-31"  # type: ignore[attr-defined]
    assert request.end.date() == date(2025, 1, 3)  # type: ignore[attr-defined]
    assert bars["symbol"].tolist() == ["AAA"]
    assert set(bars["feed"]) == {"sip"}


def test_one_minute_partition_grid_is_stable_and_separate() -> None:
    assert SIP_ONE_MINUTE_NAMESPACE == "alpaca_sip_1min_v1"
    specs = partition_specs(
        symbols=("AAA", "BBB", "CCC"),
        start=date(2025, 1, 2),
        end=date(2025, 2, 3),
        batch_size=2,
    )
    assert len(specs) == 4
    assert [spec["global_shard_index"] for spec in specs] == [0, 1, 2, 3]
    assert specs[0]["request"]["bar_size"] == "1min"
    assert specs[0]["request"]["asof"] == "2025-01-31"
    assert specs[2]["request"]["asof"] == "2025-02-03"
    assert specs[0]["stem"].startswith("2025-01-batch-0000-")
    assert specs == partition_specs(
        symbols=("AAA", "BBB", "CCC"),
        start=date(2025, 1, 2),
        end=date(2025, 2, 3),
        batch_size=2,
    )


def test_downloader_rejects_missing_credentials() -> None:
    with pytest.raises(RuntimeError, match="ALPACA_SIP_ONE_MINUTE_CREDENTIAL_MISSING"):
        ReadOnlyAlpacaSipOneMinuteDownloader.from_environment(environ={})
