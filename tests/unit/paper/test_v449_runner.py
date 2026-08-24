from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from scripts.run_v449_alpaca_paper import _target_complete

SESSION = date(2026, 8, 24)
OPEN = datetime(2026, 8, 24, 13, 30, tzinfo=UTC)


def _bars(*, missing: dict[str, set[int]] | None = None) -> pd.DataFrame:
    omitted = missing or {}
    rows: list[dict[str, object]] = []
    for symbol in ("TQQQ", "SOXL", "XLC"):
        for minute in range(120):
            if minute in omitted.get(symbol, set()):
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": OPEN + timedelta(minutes=minute),
                    "open": 100.0,
                    "high": 100.0,
                    "low": 100.0,
                    "close": 100.0,
                    "volume": 1.0,
                }
            )
    return pd.DataFrame(rows)


def test_target_complete_allows_sparse_minutes_and_ignores_context_etfs() -> None:
    bars = _bars(
        missing={
            "TQQQ": {1, 2, 3, 4, 16, 17, 18},
            "XLC": set(range(90)),
        }
    )

    assert _target_complete(bars, SESSION, through_bar=23) is True


def test_target_complete_rejects_a_wholly_missing_traded_asset_bucket() -> None:
    bars = _bars(missing={"TQQQ": set(range(80, 85))})

    assert _target_complete(bars, SESSION, through_bar=23) is False


def test_target_complete_does_not_accept_a_future_bucket_for_a_missing_bucket() -> None:
    bars = _bars(missing={"SOXL": set(range(55, 60))})

    assert _target_complete(bars, SESSION, through_bar=23) is False
