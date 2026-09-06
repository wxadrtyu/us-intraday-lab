from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from us_intraday_lab.data.alpaca_iex_acquisition import normalize_alpaca_bars
from us_intraday_lab.data.calendar import expected_minute_index
from us_intraday_lab.data.market_minute_acquisition import (
    acquire_eligible_minutes,
    quarantine_invalid_symbol_sessions,
)


def test_only_eligible_symbol_months_are_acquired_and_blind_is_sealed(tmp_path: Path) -> None:
    decisions = pd.DataFrame(
        {
            "month": [date(2026, 4, 1), date(2026, 4, 1)],
            "symbol": ["GOOD", "NOPE"],
            "eligible": [True, False],
        }
    )
    decisions_path = tmp_path / "decisions.parquet"
    decisions.to_parquet(decisions_path, index=False)

    class FakeDownloader:
        def fetch(self, *, symbols: tuple[str, ...], start: date, end: date) -> pd.DataFrame:
            assert symbols == ("GOOD",)
            session = date(2026, 4, 1)
            source = pd.DataFrame(
                {
                    "symbol": "GOOD",
                    "timestamp": expected_minute_index(session),
                    "open": 10.0,
                    "high": 10.1,
                    "low": 9.9,
                    "close": 10.0,
                    "volume": 1000.0,
                }
            )
            return normalize_alpaca_bars(source, ingested_at=datetime(2026, 5, 1, tzinfo=UTC))

    records = acquire_eligible_minutes(
        root=tmp_path,
        decisions_path=decisions_path,
        downloader=FakeDownloader(),  # type: ignore[arg-type]
    )

    assert len(records) == 1
    assert records[0]["symbols"] == ["GOOD"]
    assert records[0]["blind_test_candidate"] is True
    assert records[0]["strategy_metrics_permitted"] is False
    assert records[0]["row_count"] == 390


def test_corrupt_bar_quarantines_the_complete_symbol_session() -> None:
    session = date(2021, 6, 11)
    source = pd.DataFrame(
        {
            "symbol": "T",
            "timestamp": expected_minute_index(session),
            "open": 29.0,
            "high": 29.1,
            "low": 28.9,
            "close": 29.0,
            "volume": 1000.0,
        }
    )
    bars = normalize_alpaca_bars(source)
    bars.loc[100, "low"] = 0.0

    accepted, quarantined, groups = quarantine_invalid_symbol_sessions(bars)

    assert accepted.empty
    assert len(quarantined) == 390
    assert groups == [{"symbol": "T", "session_date": "2021-06-11"}]
