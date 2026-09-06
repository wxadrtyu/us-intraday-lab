from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from us_intraday_lab.data.us_market_acquisition import (
    ASSET_ENDPOINT,
    ReadOnlyDailyBarDownloader,
    acquire_daily_shards,
    fetch_asset_catalog,
    normalize_asset_catalog,
    primary_exchange_symbols,
    publish_asset_catalog,
    unqueryable_primary_symbols,
)


def _records() -> list[dict[str, object]]:
    return [
        {
            "id": "2",
            "class": "us_equity",
            "exchange": "OTC",
            "symbol": "ZZZ",
            "name": "Z",
            "status": "inactive",
            "tradable": False,
        },
        {
            "id": "1",
            "class": "us_equity",
            "exchange": "NASDAQ",
            "symbol": "abc",
            "name": "A",
            "status": "active",
            "tradable": True,
            "fractionable": True,
        },
        {
            "id": "3",
            "class": "us_equity",
            "exchange": "NYSE",
            "symbol": "ABC",
            "name": "Old A",
            "status": "inactive",
            "tradable": False,
        },
        {
            "id": "4",
            "class": "us_equity",
            "exchange": "NYSE",
            "symbol": "0029900E0",
            "name": "Non-ticker entitlement",
            "status": "inactive",
            "tradable": False,
        },
    ]


def test_catalog_fetch_is_one_allowlisted_get_and_does_not_disclose_credentials() -> None:
    observed: dict[str, object] = {}

    def fake_get(url: str, headers: dict[str, str]) -> object:
        observed.update(url=url, headers=headers)
        return _records()

    records = fetch_asset_catalog(
        environ={"ALPACA_PAPER_API_KEY": "key", "ALPACA_PAPER_SECRET_KEY": "secret"},
        json_get=fake_get,
    )

    assert records == _records()
    assert observed["url"] == ASSET_ENDPOINT
    assert observed["headers"] == {
        "APCA-API-KEY-ID": "key",
        "APCA-API-SECRET-KEY": "secret",
    }


def test_catalog_preserves_inactive_ids_and_returns_unique_primary_symbols(tmp_path: Path) -> None:
    frame = normalize_asset_catalog(_records())
    manifest = publish_asset_catalog(
        frame, root=tmp_path, retrieved_at=datetime(2026, 9, 6, tzinfo=UTC)
    )

    assert manifest["row_count"] == 4
    assert manifest["inactive_count"] == 3
    assert manifest["primary_exchange_count"] == 3
    assert primary_exchange_symbols(frame) == ("ABC",)
    assert unqueryable_primary_symbols(frame) == ("0029900E0",)
    snapshot = tmp_path / "data" / "catalog" / "us_equity_assets" / manifest["dataset_id"]
    assert (snapshot / "assets.parquet").is_file()
    assert (snapshot / "manifest.json").is_file()


def test_daily_acquisition_isolates_one_provider_rejected_symbol(tmp_path: Path) -> None:
    class FakeDownloader:
        def fetch(
            self, *, symbols: tuple[str, ...], start: date, end: date, asof: date
        ) -> pd.DataFrame:
            if "BAD" in symbols:
                raise RuntimeError('{"message":"invalid symbol: BAD"}')
            return pd.DataFrame(
                {
                    "symbol": ["ABC"],
                    "timestamp": [pd.Timestamp("2022-01-03T05:00:00Z")],
                    "close": [10.0],
                }
            )

    records = acquire_daily_shards(
        root=tmp_path,
        downloader=FakeDownloader(),  # type: ignore[arg-type]
        symbols=("ABC", "BAD"),
        start=date(2022, 1, 1),
        end=date(2022, 12, 31),
        batch_size=100,
        sleep=lambda _: None,
    )

    assert len(records) == 1
    assert records[0]["provider_rejected_symbols"] == ["BAD"]
    assert records[0]["row_count"] == 1


def test_daily_request_advances_inclusive_end_by_one_day() -> None:
    class FakeClient:
        request: object | None = None

        def get_stock_bars(self, request: object) -> object:
            self.request = request
            return SimpleNamespace(df=pd.DataFrame())

    client = FakeClient()
    ReadOnlyDailyBarDownloader(client).fetch(
        symbols=("SPY",),
        start=date(2025, 1, 1),
        end=date(2025, 12, 31),
        asof=date(2025, 12, 31),
    )

    assert client.request is not None
    assert client.request.end.date() == date(2026, 1, 1)  # type: ignore[attr-defined]
