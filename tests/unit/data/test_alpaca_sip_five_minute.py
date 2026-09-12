from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from us_intraday_lab.data.alpaca_sip_five_minute import (
    SIP_FIVE_MINUTE_NAMESPACE,
    ReadOnlyAlpacaSipFiveMinuteDownloader,
    acquire_sip_five_minute_shards,
    load_frozen_candidate_symbols,
    validate_sip_five_minute_source,
)


def _five_minute_frame(symbol: str = "aaa") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [symbol, symbol],
            "timestamp": [
                pd.Timestamp("2025-01-02T14:30:00Z"),
                pd.Timestamp("2025-01-02T14:35:00Z"),
            ],
            "open": [100.0, 100.5],
            "high": [101.0, 101.5],
            "low": [99.5, 100.0],
            "close": [100.5, 101.0],
            "volume": [10_000.0, 12_000.0],
            "trade_count": [100.0, 120.0],
            "vwap": [100.25, 100.75],
        }
    )


class FakeHistoricalClient:
    def __init__(self, frame: pd.DataFrame) -> None:
        self.frame = frame
        self.request: object | None = None

    def get_stock_bars(self, request: object) -> object:
        self.request = request
        return SimpleNamespace(df=self.frame)


def test_request_is_split_adjusted_sip_five_minutes_and_preserves_asof() -> None:
    client = FakeHistoricalClient(_five_minute_frame())

    result = ReadOnlyAlpacaSipFiveMinuteDownloader(client).fetch(
        symbols=("AAA",),
        start=date(2025, 1, 2),
        end=date(2025, 1, 2),
        asof=date(2025, 1, 31),
    )

    assert client.request is not None
    assert client.request.timeframe.amount == 5  # type: ignore[attr-defined]
    assert client.request.timeframe.unit.value == "Min"  # type: ignore[attr-defined]
    assert client.request.feed.value == "sip"  # type: ignore[attr-defined]
    assert client.request.adjustment.value == "split"  # type: ignore[attr-defined]
    assert client.request.asof == "2025-01-31"  # type: ignore[attr-defined]
    assert client.request.end.date() == date(2025, 1, 3)  # type: ignore[attr-defined]
    assert result["symbol"].tolist() == ["AAA", "AAA"]
    assert set(result["asof"]) == {date(2025, 1, 31)}
    assert set(result["provider"]) == {"alpaca"}
    assert set(result["feed"]) == {"sip"}


def test_environment_fails_closed_without_credentials() -> None:
    with pytest.raises(RuntimeError, match="ALPACA_SIP_FIVE_MINUTE_CREDENTIAL_MISSING"):
        ReadOnlyAlpacaSipFiveMinuteDownloader.from_environment(environ={})


def test_downloader_retains_only_xnys_regular_session_bars() -> None:
    frame = pd.concat(
        [
            _five_minute_frame().iloc[[0]],
            _five_minute_frame().iloc[[0]].assign(
                timestamp=pd.Timestamp("2025-01-02T14:25:00Z")
            ),
            _five_minute_frame().iloc[[0]].assign(
                timestamp=pd.Timestamp("2025-01-02T21:00:00Z")
            ),
        ],
        ignore_index=True,
    )
    client = FakeHistoricalClient(frame)

    result = ReadOnlyAlpacaSipFiveMinuteDownloader(client).fetch(
        symbols=("AAA",),
        start=date(2025, 1, 2),
        end=date(2025, 1, 2),
        asof=date(2025, 1, 31),
    )

    assert result["timestamp"].tolist() == [pd.Timestamp("2025-01-02T14:30:00Z")]
    assert result.attrs["provider_source_rows"] == 3
    assert result.attrs["excluded_out_of_session_rows"] == 2


def test_shard_bounds_are_disjoint_deterministic_and_resumable(tmp_path: Path) -> None:
    class FakeDownloader:
        def __init__(self) -> None:
            self.calls = 0

        def fetch(self, *, symbols, start, end, asof):
            self.calls += 1
            frame = _five_minute_frame(symbols[0])
            session_day = date(2025, 1, 2) if start.month == 1 else date(2025, 2, 3)
            frame["timestamp"] = pd.date_range(
                pd.Timestamp(session_day, tz=UTC) + pd.Timedelta(hours=14, minutes=30),
                periods=2,
                freq="5min",
            )
            return frame.assign(asof=asof, provider="alpaca", feed="sip")

    downloader = FakeDownloader()
    kwargs = {
        "root": tmp_path,
        "downloader": downloader,
        "symbols": ("AAA", "BBB"),
        "start": date(2025, 1, 1),
        "end": date(2025, 2, 28),
        "batch_size": 1,
        "shard_start": 1,
        "shard_stop": 3,
        "sleep": lambda _: None,
    }
    first = acquire_sip_five_minute_shards(**kwargs)
    resumed = acquire_sip_five_minute_shards(**kwargs)

    assert downloader.calls == 2
    assert first == resumed
    assert [record["global_shard_index"] for record in first] == [1, 2]
    assert all(record["source_namespace"] == SIP_FIVE_MINUTE_NAMESPACE for record in first)
    assert all(record["bar_size"] == "5min" for record in first)
    assert all(Path(str(record["manifest_path"])).is_file() for record in first)


def test_resume_rejects_manifest_request_identity_collision(tmp_path: Path) -> None:
    class FakeDownloader:
        def fetch(self, *, symbols, start, end, asof):
            return _five_minute_frame(symbols[0]).assign(
                asof=asof, provider="alpaca", feed="sip"
            )

    kwargs = {
        "root": tmp_path,
        "downloader": FakeDownloader(),
        "symbols": ("AAA",),
        "start": date(2025, 1, 1),
        "end": date(2025, 1, 31),
        "batch_size": 100,
        "sleep": lambda _: None,
    }
    record = acquire_sip_five_minute_shards(**kwargs)[0]
    manifest = Path(str(record["manifest_path"]))
    payload = json.loads(manifest.read_text("utf-8"))
    payload["request"]["feed"] = "iex"
    manifest.write_text(json.dumps(payload), "utf-8")

    with pytest.raises(ValueError, match="request identity"):
        acquire_sip_five_minute_shards(**kwargs)


def test_validation_requires_the_complete_expected_grid(tmp_path: Path) -> None:
    class FakeDownloader:
        def fetch(self, *, symbols, start, end, asof):
            session = date(2025, 1, 2) if start.month == 1 else date(2025, 2, 3)
            return _five_minute_frame(symbols[0]).iloc[[0]].assign(
                timestamp=pd.Timestamp(datetime.combine(session, datetime.min.time(), UTC))
                + pd.Timedelta(hours=14, minutes=30),
                asof=asof,
                provider="alpaca",
                feed="sip",
            )

    acquire_sip_five_minute_shards(
        root=tmp_path,
        downloader=FakeDownloader(),
        symbols=("AAA",),
        start=date(2025, 1, 1),
        end=date(2025, 2, 28),
        batch_size=100,
        sleep=lambda _: None,
    )
    source = tmp_path / "data" / "staging" / SIP_FIVE_MINUTE_NAMESPACE
    manifest = next(source.glob("2025-01-*.json"))
    manifest.with_suffix(".parquet").unlink()
    manifest.unlink()

    with pytest.raises(ValueError, match="expected acquisition grid mismatch"):
        validate_sip_five_minute_source(
            root=tmp_path,
            symbols=("AAA",),
            start=date(2025, 1, 1),
            end=date(2025, 2, 28),
            batch_size=100,
        )


def test_provider_empty_response_fails_without_publishing_a_partition(tmp_path: Path) -> None:
    class EmptyDownloader:
        def fetch(self, *, symbols, start, end, asof):
            return pd.DataFrame(
                columns=[
                    "symbol", "timestamp", "open", "high", "low", "close",
                    "volume", "trade_count", "vwap", "asof", "provider", "feed",
                ]
            )

    with pytest.raises(RuntimeError, match="ALPACA_SIP_FIVE_MINUTE_EMPTY_RESPONSE"):
        acquire_sip_five_minute_shards(
            root=tmp_path,
            downloader=EmptyDownloader(),
            symbols=("AAA",),
            start=date(2025, 1, 1),
            end=date(2025, 1, 31),
            batch_size=100,
            sleep=lambda _: None,
        )
    source = tmp_path / "data" / "staging" / SIP_FIVE_MINUTE_NAMESPACE
    assert not tuple(source.glob("*.parquet"))
    assert not tuple(path for path in source.glob("*.json") if "contract" not in path.name)


def test_namespace_rejects_a_different_batch_contract_before_redownloading(
    tmp_path: Path,
) -> None:
    class FakeDownloader:
        def __init__(self) -> None:
            self.calls = 0

        def fetch(self, *, symbols, start, end, asof):
            self.calls += 1
            frames = [_five_minute_frame(symbol) for symbol in symbols]
            return pd.concat(frames, ignore_index=True).assign(
                asof=asof, provider="alpaca", feed="sip"
            )

    downloader = FakeDownloader()
    common = {
        "root": tmp_path,
        "downloader": downloader,
        "symbols": ("AAA", "BBB"),
        "start": date(2025, 1, 1),
        "end": date(2025, 1, 31),
        "sleep": lambda _: None,
    }
    acquire_sip_five_minute_shards(**common, batch_size=1)
    assert downloader.calls == 2

    with pytest.raises(ValueError, match="acquisition contract mismatch"):
        acquire_sip_five_minute_shards(**common, batch_size=2)
    assert downloader.calls == 2


def test_resume_rejects_an_orphan_temporary_partition_before_redownloading(
    tmp_path: Path,
) -> None:
    class FakeDownloader:
        def __init__(self) -> None:
            self.calls = 0

        def fetch(self, *, symbols, start, end, asof):
            self.calls += 1
            return _five_minute_frame(symbols[0]).assign(
                asof=asof, provider="alpaca", feed="sip"
            )

    downloader = FakeDownloader()
    kwargs = {
        "root": tmp_path,
        "downloader": downloader,
        "symbols": ("AAA",),
        "start": date(2025, 1, 1),
        "end": date(2025, 1, 31),
        "batch_size": 100,
        "sleep": lambda _: None,
    }
    record = acquire_sip_five_minute_shards(**kwargs)[0]
    manifest = Path(str(record["manifest_path"]))
    parquet = manifest.with_suffix(".parquet")
    temporary = parquet.with_suffix(".tmp.parquet")
    parquet.replace(temporary)
    manifest.unlink()

    with pytest.raises(ValueError, match="temporary SIP five-minute partition"):
        acquire_sip_five_minute_shards(**kwargs)
    assert downloader.calls == 1


def test_validator_rejects_residual_out_of_session_content_even_with_fresh_hash(
    tmp_path: Path,
) -> None:
    class FakeDownloader:
        def fetch(self, *, symbols, start, end, asof):
            return _five_minute_frame(symbols[0]).assign(
                asof=asof, provider="alpaca", feed="sip"
            )

    record = acquire_sip_five_minute_shards(
        root=tmp_path,
        downloader=FakeDownloader(),
        symbols=("AAA",),
        start=date(2025, 1, 1),
        end=date(2025, 1, 31),
        batch_size=100,
        sleep=lambda _: None,
    )[0]
    manifest = Path(str(record["manifest_path"]))
    parquet = manifest.with_suffix(".parquet")
    frame = pd.read_parquet(parquet)
    frame.loc[0, "timestamp"] = pd.Timestamp("2025-01-02T14:25:00Z")
    frame.to_parquet(parquet, index=False, compression="zstd")
    payload = json.loads(manifest.read_text("utf-8"))
    payload["content_sha256"] = hashlib.sha256(parquet.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(payload), "utf-8")

    with pytest.raises(ValueError, match="outside_regular_session"):
        validate_sip_five_minute_source(
            root=tmp_path,
            symbols=("AAA",),
            start=date(2025, 1, 1),
            end=date(2025, 1, 31),
            batch_size=100,
        )


def test_resume_revalidates_manifest_row_count_before_reuse(tmp_path: Path) -> None:
    class FakeDownloader:
        def fetch(self, *, symbols, start, end, asof):
            return _five_minute_frame(symbols[0]).assign(
                asof=asof, provider="alpaca", feed="sip"
            )

    kwargs = {
        "root": tmp_path,
        "downloader": FakeDownloader(),
        "symbols": ("AAA",),
        "start": date(2025, 1, 1),
        "end": date(2025, 1, 31),
        "batch_size": 100,
        "sleep": lambda _: None,
    }
    record = acquire_sip_five_minute_shards(**kwargs)[0]
    manifest = Path(str(record["manifest_path"]))
    payload = json.loads(manifest.read_text("utf-8"))
    payload["row_count"] = 999
    manifest.write_text(json.dumps(payload), "utf-8")

    with pytest.raises(ValueError, match="row-count"):
        acquire_sip_five_minute_shards(**kwargs)


def test_acquisition_code_has_no_trading_client_imports() -> None:
    repo = Path(__file__).parents[3]
    paths = (
        repo / "src/us_intraday_lab/data/alpaca_sip_five_minute.py",
        repo / "scripts/acquire_us_market_sip_five_minute.py",
    )
    imported: list[str] = []
    for path in paths:
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
            elif isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
    assert not [name for name in imported if name.startswith("alpaca.trading")]


@pytest.mark.parametrize(
    ("column", "value"),
    (("trade_count", -1.0), ("vwap", -5.0), ("close", float("inf"))),
)
def test_quality_rejects_invalid_optional_or_nonfinite_values(
    tmp_path: Path, column: str, value: float
) -> None:
    class FakeDownloader:
        def fetch(self, *, symbols, start, end, asof):
            frame = _five_minute_frame(symbols[0]).assign(
                asof=asof, provider="alpaca", feed="sip"
            )
            frame.loc[0, column] = value
            return frame

    with pytest.raises(ValueError, match="quality failure"):
        acquire_sip_five_minute_shards(
            root=tmp_path,
            downloader=FakeDownloader(),
            symbols=("AAA",),
            start=date(2025, 1, 1),
            end=date(2025, 1, 31),
            batch_size=100,
            sleep=lambda _: None,
        )


def test_frozen_candidate_loader_rejects_truncated_asset_snapshot(tmp_path: Path) -> None:
    snapshot = tmp_path / "alpaca-us-equity-assets-frozen"
    snapshot.mkdir()
    assets = snapshot / "assets.parquet"
    pd.DataFrame({"symbol": ["AAA"], "exchange": ["NASDAQ"]}).to_parquet(assets)
    protocol = tmp_path / "protocol.json"
    protocol.write_text(
        json.dumps(
            {
                "candidate_asset_snapshot": snapshot.name,
                "candidate_symbols": 2,
                "candidate_symbols_sha256": hashlib.sha256(b"AAA\nBBB").hexdigest(),
            }
        ),
        "utf-8",
    )

    with pytest.raises(ValueError, match="frozen candidate universe"):
        load_frozen_candidate_symbols(assets_path=assets, protocol_path=protocol)


def test_cli_exposes_disjoint_shard_bounds() -> None:
    script = Path(__file__).parents[3] / "scripts" / "acquire_us_market_sip_five_minute.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "--shard-start" in result.stdout
    assert "--shard-stop" in result.stdout
