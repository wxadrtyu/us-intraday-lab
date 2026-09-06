from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from us_intraday_lab.data.us_market_acquisition import (
    ASSET_ENDPOINT,
    fetch_asset_catalog,
    normalize_asset_catalog,
    primary_exchange_symbols,
    publish_asset_catalog,
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

    assert manifest["row_count"] == 3
    assert manifest["inactive_count"] == 2
    assert manifest["primary_exchange_count"] == 2
    assert primary_exchange_symbols(frame) == ("ABC",)
    snapshot = tmp_path / "data" / "catalog" / "us_equity_assets" / manifest["dataset_id"]
    assert (snapshot / "assets.parquet").is_file()
    assert (snapshot / "manifest.json").is_file()
