from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from us_intraday_lab.data.alpaca_sip_one_minute import (
    SIP_ONE_MINUTE_NAMESPACE,
    ReadOnlyAlpacaSipOneMinuteDownloader,
    acquire_sip_one_minute_shards,
    normalize_one_minute_bars,
    partition_specs,
    quality_report,
    validate_sip_one_minute_source,
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


def _raw_rows() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["aaa", "aaa", "aaa"],
            "timestamp": [
                pd.Timestamp("2025-01-02T14:29:00Z"),
                pd.Timestamp("2025-01-02T14:30:00Z"),
                pd.Timestamp("2025-01-02T21:00:00Z"),
            ],
            "open": [100.0, 100.0, 100.0],
            "high": [101.0, 101.0, 101.0],
            "low": [99.0, 99.0, 99.0],
            "close": [100.5, 100.5, 100.5],
            "volume": [1000.0, 1000.0, 1000.0],
            "trade_count": [20.0, 20.0, 20.0],
            "vwap": [100.2, 100.2, 100.2],
        }
    )


def test_normalization_retains_only_actual_regular_session_and_accounts_rows() -> None:
    frame = normalize_one_minute_bars(_raw_rows(), asof=date(2025, 1, 31))
    assert len(frame) == 1
    assert frame["symbol"].tolist() == ["AAA"]
    assert frame.attrs["provider_source_rows"] == 3
    assert frame.attrs["excluded_out_of_session_rows"] == 2
    assert (
        quality_report(
            frame,
            requested=("AAA",),
            start=date(2025, 1, 2),
            end=date(2025, 1, 2),
            asof=date(2025, 1, 31),
        )["returned_rows"]
        == 1
    )


@pytest.mark.parametrize(
    ("column", "value", "reason"),
    [
        ("timestamp", pd.Timestamp("2025-01-02T14:30:01Z"), "off_grid"),
        ("open", 0.0, "invalid_ohlc"),
        ("high", 99.0, "invalid_ohlc"),
        ("volume", -1.0, "invalid_ohlc"),
        ("trade_count", -1.0, "invalid_trade_count"),
        ("vwap", 0.0, "invalid_vwap"),
        ("symbol", "BBB", "unexpected_symbols"),
    ],
)
def test_quality_rejects_malformed_source_row(column: str, value: object, reason: str) -> None:
    frame = normalize_one_minute_bars(_raw_rows(), asof=date(2025, 1, 31))
    frame.loc[frame.index[0], column] = value
    with pytest.raises(ValueError, match=reason):
        quality_report(
            frame,
            requested=("AAA",),
            start=date(2025, 1, 2),
            end=date(2025, 1, 2),
            asof=date(2025, 1, 31),
        )


def test_quality_rejects_duplicate_symbol_minute() -> None:
    frame = normalize_one_minute_bars(_raw_rows(), asof=date(2025, 1, 31))
    duplicate = pd.concat([frame, frame], ignore_index=True)
    with pytest.raises(ValueError, match="duplicates"):
        quality_report(
            duplicate,
            requested=("AAA",),
            start=date(2025, 1, 2),
            end=date(2025, 1, 2),
            asof=date(2025, 1, 31),
        )


class FakeDownloader:
    def __init__(self) -> None:
        self.calls = 0

    def fetch(
        self, *, symbols: tuple[str, ...], start: date, end: date, asof: date
    ) -> pd.DataFrame:
        self.calls += 1
        frame = normalize_one_minute_bars(_raw_rows(), asof=asof)
        frame["symbol"] = symbols[0]
        return frame


def test_shard_is_atomic_hashed_and_resumable(tmp_path: Path) -> None:
    downloader = FakeDownloader()
    kwargs = {
        "root": tmp_path,
        "downloader": downloader,
        "symbols": ("AAA",),
        "start": date(2025, 1, 2),
        "end": date(2025, 1, 2),
        "batch_size": 1,
        "shard_start": 0,
        "shard_stop": 1,
    }
    first = acquire_sip_one_minute_shards(**kwargs)
    assert len(first) == 1
    assert first[0]["request"]["bar_size"] == "1min"
    assert first[0]["provider_source_rows"] == 3
    assert first[0]["excluded_out_of_session_rows"] == 2
    assert first[0]["content_sha256"]
    assert validate_sip_one_minute_source(
        root=tmp_path, symbols=("AAA",), start=date(2025, 1, 2), end=date(2025, 1, 2), batch_size=1
    ) == {"partitions": 1, "rows": 1}
    assert acquire_sip_one_minute_shards(**kwargs) == first
    assert downloader.calls == 1


def test_shard_rejects_corruption_and_partial_publication(tmp_path: Path) -> None:
    kwargs = {
        "root": tmp_path,
        "downloader": FakeDownloader(),
        "symbols": ("AAA",),
        "start": date(2025, 1, 2),
        "end": date(2025, 1, 2),
        "batch_size": 1,
        "shard_start": 0,
        "shard_stop": 1,
    }
    acquire_sip_one_minute_shards(**kwargs)
    source = tmp_path / "data" / "staging" / SIP_ONE_MINUTE_NAMESPACE
    parquet = next(source.glob("*.parquet"))
    parquet.write_bytes(parquet.read_bytes() + b"corrupt")
    with pytest.raises(ValueError, match="provenance"):
        acquire_sip_one_minute_shards(**kwargs)


def test_shard_refuses_missing_contract_or_identity_mismatch(tmp_path: Path) -> None:
    kwargs = {
        "root": tmp_path,
        "downloader": FakeDownloader(),
        "symbols": ("AAA",),
        "start": date(2025, 1, 2),
        "end": date(2025, 1, 2),
        "batch_size": 1,
        "shard_start": 0,
        "shard_stop": 1,
    }
    acquire_sip_one_minute_shards(**kwargs)
    source = tmp_path / "data" / "staging" / SIP_ONE_MINUTE_NAMESPACE
    manifest = next(
        path for path in source.glob("*.json") if path.name != "acquisition_contract.json"
    )
    record = json.loads(manifest.read_text("utf-8"))
    record["request"]["feed"] = "iex"
    manifest.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="identity"):
        acquire_sip_one_minute_shards(**kwargs)
    manifest.unlink()
    with pytest.raises(ValueError, match="partial"):
        acquire_sip_one_minute_shards(**kwargs)
    (source / "acquisition_contract.json").unlink()
    with pytest.raises(ValueError, match="contract missing"):
        acquire_sip_one_minute_shards(**kwargs)


def test_shard_requires_finite_stop(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="finite"):
        acquire_sip_one_minute_shards(
            root=tmp_path,
            downloader=FakeDownloader(),
            symbols=("AAA",),
            start=date(2025, 1, 2),
            end=date(2025, 1, 2),
            batch_size=1,
        )


def test_shard_records_provider_rejection_and_refuses_ledger_tamper(tmp_path: Path) -> None:
    class RejectingDownloader(FakeDownloader):
        def fetch(
            self, *, symbols: tuple[str, ...], start: date, end: date, asof: date
        ) -> pd.DataFrame:
            if "BBB" in symbols:
                raise ValueError("invalid symbol: BBB")
            return super().fetch(symbols=symbols, start=start, end=end, asof=asof)

    kwargs = {
        "root": tmp_path,
        "downloader": RejectingDownloader(),
        "symbols": ("AAA", "BBB"),
        "start": date(2025, 1, 2),
        "end": date(2025, 1, 2),
        "batch_size": 2,
        "shard_start": 0,
        "shard_stop": 1,
    }
    record = acquire_sip_one_minute_shards(**kwargs)[0]
    assert record["provider_rejected_symbols"] == ["BBB"]
    source = tmp_path / "data" / "staging" / SIP_ONE_MINUTE_NAMESPACE
    manifest = next(
        path for path in source.glob("*.json") if path.name != "acquisition_contract.json"
    )
    record["provider_rejected_symbols"] = ["AAA"]
    manifest.write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(ValueError, match="rejection ledger"):
        acquire_sip_one_minute_shards(**kwargs)
