from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from us_intraday_lab.data.alpaca_sip_daily import (
    ReadOnlyAlpacaSipDailyDownloader,
    acquire_sip_daily_shards,
    validate_sip_daily_source,
)


def _daily_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["aapl", "old"],
            "timestamp": [
                pd.Timestamp("2022-01-03T05:00:00Z"),
                pd.Timestamp("2022-01-03T05:00:00Z"),
            ],
            "open": [177.83, 10.0],
            "high": [182.88, 10.5],
            "low": [177.71, 9.8],
            "close": [182.01, 10.2],
            "volume": [104_487_900.0, 2_000_000.0],
            "trade_count": [895_426.0, 5_000.0],
            "vwap": [180.4343, 10.1],
        }
    )


class FakeHistoricalClient:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.request: object | None = None

    def get_stock_bars(self, request: object) -> object:
        self.request = request
        return SimpleNamespace(df=self.frame)


def test_sip_daily_request_is_sip_and_preserves_asof() -> None:
    client = FakeHistoricalClient(_daily_frame())

    result = ReadOnlyAlpacaSipDailyDownloader(client).fetch(
        symbols=("AAPL", "OLD"),
        start=date(2022, 1, 1),
        end=date(2022, 1, 31),
        asof=date(2022, 1, 31),
    )

    assert client.request is not None
    assert client.request.feed.value == "sip"  # type: ignore[attr-defined]
    assert client.request.asof == "2022-01-31"  # type: ignore[attr-defined]
    assert client.request.end.date() == date(2022, 2, 1)  # type: ignore[attr-defined]
    assert result["symbol"].tolist() == ["AAPL", "OLD"]
    assert set(result["feed"]) == {"sip"}
    assert set(result["provider"]) == {"alpaca"}
    assert set(result["asof"]) == {date(2022, 1, 31)}


def test_sip_daily_environment_fails_closed_without_credentials() -> None:
    with pytest.raises(RuntimeError, match="ALPACA_SIP_DAILY_CREDENTIAL_MISSING"):
        ReadOnlyAlpacaSipDailyDownloader.from_environment(environ={})


def test_sip_daily_acquisition_is_immutable_and_resumable(tmp_path) -> None:
    class FakeDownloader:
        calls = 0

        def fetch(self, *, symbols, start, end, asof):
            self.calls += 1
            frame = _daily_frame().loc[lambda value: value["symbol"].str.upper().isin(symbols)]
            dates = pd.to_datetime(frame["timestamp"], utc=True).dt.date
            return frame.loc[(dates >= start) & (dates <= end)]

    downloader = FakeDownloader()
    records = acquire_sip_daily_shards(
        root=tmp_path,
        downloader=downloader,
        symbols=("AAPL", "OLD"),
        start=date(2022, 1, 1),
        end=date(2022, 12, 31),
        batch_size=100,
        sleep=lambda _: None,
    )
    resumed = acquire_sip_daily_shards(
        root=tmp_path,
        downloader=downloader,
        symbols=("AAPL", "OLD"),
        start=date(2022, 1, 1),
        end=date(2022, 12, 31),
        batch_size=100,
        sleep=lambda _: None,
    )

    assert downloader.calls == 12
    assert records == resumed
    assert records[0]["feed"] == "sip"
    assert records[0]["source_namespace"] == "alpaca_sip_1day_v2"
    assert records[0]["row_count"] == 2
    assert records[0]["content_sha256"]


def test_sip_daily_acquisition_isolates_provider_rejected_symbol(tmp_path) -> None:
    class FakeDownloader:
        def fetch(self, *, symbols, start, end, asof):
            if "BAD" in symbols:
                raise RuntimeError('{"message":"invalid symbol: BAD"}')
            frame = _daily_frame().iloc[:1]
            dates = pd.to_datetime(frame["timestamp"], utc=True).dt.date
            return frame.loc[(dates >= start) & (dates <= end)]

    records = acquire_sip_daily_shards(
        root=tmp_path,
        downloader=FakeDownloader(),
        symbols=("AAPL", "BAD"),
        start=date(2022, 1, 1),
        end=date(2022, 12, 31),
        sleep=lambda _: None,
    )

    assert records[0]["provider_rejected_symbols"] == ["BAD"]


def test_sip_daily_acquisition_partitions_by_month_and_preserves_request_identity(tmp_path) -> None:
    class FakeDownloader:
        def fetch(self, *, symbols, start, end, asof):
            return pd.DataFrame(columns=_daily_frame().columns)

    records = acquire_sip_daily_shards(
        root=tmp_path,
        downloader=FakeDownloader(),
        symbols=("AAPL",),
        start=date(2022, 1, 1),
        end=date(2022, 2, 28),
        sleep=lambda _: None,
    )

    assert [(record["start"], record["end"], record["asof"]) for record in records] == [
        ("2022-01-01", "2022-01-31", "2022-01-31"),
        ("2022-02-01", "2022-02-28", "2022-02-28"),
    ]
    assert all(record["request_identity_sha256"] for record in records)
    assert all(record["retrieved_at"] for record in records)
    assert all(record["quality"]["returned_rows"] == 0 for record in records)


def test_sip_daily_source_validation_rejects_orphan_partition(tmp_path) -> None:
    source = tmp_path / "data" / "staging" / "alpaca_sip_1day_v2"
    source.mkdir(parents=True)
    (source / "orphan.parquet").touch()

    with pytest.raises(ValueError, match="partition pairing failure"):
        validate_sip_daily_source(root=tmp_path)
