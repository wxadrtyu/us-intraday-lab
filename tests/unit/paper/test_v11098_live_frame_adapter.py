from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from v11098_live_frame_adapter import _bucket, feature_cube_from_bars


def _bars(sessions: int = 61) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-02", periods=sessions)
    rows = []
    for offset, day in enumerate(dates):
        for symbol_index, symbol in enumerate(("SPY", "TQQQ")):
            for minute in range(390):
                timestamp = (
                    pd.Timestamp(day.date(), tz="America/New_York")
                    + pd.Timedelta(hours=9, minutes=30 + minute)
                ).tz_convert("UTC")
                price = 100.0 + offset + symbol_index + minute / 1000.0
                rows.append(
                    {
                        "timestamp": timestamp,
                        "symbol": symbol,
                        "open": price,
                        "high": price + 0.1,
                        "low": price - 0.1,
                        "close": price + 0.01,
                        "volume": 100.0,
                    }
                )
    return pd.DataFrame(rows)


def test_bucket_uses_exact_new_york_five_minute_boundaries() -> None:
    result = _bucket(_bars(1))
    first = result.loc[(result["symbol"] == "SPY") & (result["bar"] == 0)].iloc[0]
    assert first["first_minute"] == 0
    assert first["last_minute"] == 4
    assert first["volume"] == 500.0


def test_live_cube_requires_sixty_prior_sessions() -> None:
    with pytest.raises(ValueError, match="61_SESSIONS"):
        feature_cube_from_bars(_bars(60))


def test_live_cube_builds_without_future_current_session_bars() -> None:
    bars = _bars()
    last_date = bars["timestamp"].dt.tz_convert("America/New_York").dt.date.max()
    local = bars["timestamp"].dt.tz_convert("America/New_York")
    minute = (local.dt.hour - 9) * 60 + local.dt.minute - 30
    bars = bars.loc[(local.dt.date != last_date) | (minute <= 29)]
    cube = feature_cube_from_bars(bars)
    assert len(cube.sessions) == 61
    assert pd.isna(cube.closes[-1, 6, 0])
    assert pd.notna(cube.factors(5)["current_return"][-1, 0])
