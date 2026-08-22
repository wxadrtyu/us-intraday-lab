from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd


def _module():
    scripts = Path(__file__).parents[2] / "scripts"
    path = scripts / "record_twelvedata_v4_1_shadow.py"
    sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location("record_twelvedata_v4_1_shadow", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bars(symbols: tuple[str, ...], timestamp: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": list(symbols),
            "timestamp": pd.to_datetime([timestamp] * len(symbols), utc=True),
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 1.0,
        }
    )


def test_incremental_cache_reads_only_new_same_provider_interval(tmp_path, monkeypatch) -> None:
    module = _module()
    campaign_id = "campaign"
    directory = tmp_path / campaign_id
    directory.mkdir()
    symbols = ("AAA", "SPY")
    _bars(symbols, "2026-08-18T19:59:00Z").to_parquet(directory / "2026-08-18.parquet", index=False)
    calls: list[tuple[datetime, datetime]] = []

    class History:
        def fetch(self, *, symbols, start, end):
            calls.append((start, end))
            return _bars(symbols, "2026-08-19T19:59:00Z")

    class Factory:
        @staticmethod
        def from_environment(*, requests_per_minute):
            assert requests_per_minute == 8.0
            return History()

    monkeypatch.setattr(module, "TwelveDataHistory", Factory)
    monkeypatch.setattr(
        module,
        "history_bounds",
        lambda value: (
            datetime(2026, 8, 1, tzinfo=UTC),
            datetime(2026, 8, value.day + 1, tzinfo=UTC),
        ),
    )
    result = module._load_or_fetch_bars(
        cache_dir=tmp_path,
        campaign_id=campaign_id,
        session_date=date(2026, 8, 19),
        universe=("AAA",),
    )
    assert calls == [(datetime(2026, 8, 19, tzinfo=UTC), datetime(2026, 8, 20, tzinfo=UTC))]
    assert set(result["symbol"]) == set(symbols)
    assert (directory / "2026-08-19.parquet").exists()
