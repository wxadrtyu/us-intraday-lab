from datetime import date

import pandas as pd

from us_intraday_lab.data.resample import resample_minute_bars

SESSION_DATE = date(2026, 7, 2)


def _minute_bars(
    *,
    symbol: str = "SPY",
    count: int = 15,
    start: str = "2026-07-02T13:30:00Z",
) -> pd.DataFrame:
    timestamps = pd.date_range(start, periods=count, freq="min", tz="UTC")
    return pd.DataFrame(
        {
            "symbol": symbol,
            "timestamp": timestamps,
            "open": [100.0 + index for index in range(count)],
            "high": [101.0 + index for index in range(count)],
            "low": [99.0 + index for index in range(count)],
            "close": [100.5 + index for index in range(count)],
            "volume": [100 + index for index in range(count)],
            "session_date": SESSION_DATE,
        }
    )


def test_resample_anchors_five_minute_bars_at_xnys_open_and_uses_ohlcv() -> None:
    bars = _minute_bars(count=5)

    derived = resample_minute_bars(
        bars,
        bar_size="5min",
        parent_snapshot_id="snapshot-1min",
    )

    assert len(derived) == 1
    bar = derived.iloc[0]
    assert bar["available_at"] == pd.Timestamp("2026-07-02T13:35:00Z")
    assert bar["open"] == 100.0
    assert bar["high"] == 105.0
    assert bar["low"] == 99.0
    assert bar["close"] == 104.5
    assert bar["volume"] == 510
    assert bar["source_bar_size"] == "1min"
    assert bar["parent_snapshot_id"] == "snapshot-1min"


def test_resample_anchors_fifteen_minute_bars_at_xnys_open() -> None:
    bars = _minute_bars(count=15)

    derived = resample_minute_bars(
        bars,
        bar_size="15min",
        parent_snapshot_id="snapshot-1min",
    )

    assert len(derived) == 1
    assert derived.loc[0, "available_at"] == pd.Timestamp("2026-07-02T13:45:00Z")
    assert derived.loc[0, "open"] == 100.0
    assert derived.loc[0, "close"] == 114.5


def test_resample_omits_incomplete_intervals() -> None:
    bars = _minute_bars(count=9)

    derived = resample_minute_bars(
        bars,
        bar_size="5min",
        parent_snapshot_id="snapshot-1min",
    )

    assert list(derived["available_at"]) == [pd.Timestamp("2026-07-02T13:35:00Z")]


def test_resample_keeps_symbols_isolated() -> None:
    spy = _minute_bars(symbol="SPY", count=5)
    qqq = _minute_bars(symbol="QQQ", count=5)
    qqq["open"] = 200.0
    qqq["high"] = 201.0
    qqq["low"] = 199.0
    qqq["close"] = 200.5
    qqq["volume"] = 1

    derived = resample_minute_bars(
        pd.concat([spy, qqq], ignore_index=True),
        bar_size="5min",
        parent_snapshot_id="snapshot-1min",
    )

    assert list(derived["symbol"]) == ["QQQ", "SPY"]
    assert list(derived["volume"]) == [5, 510]


def test_resample_fifteen_minute_bar_cannot_see_the_next_minute() -> None:
    bars = _minute_bars(count=16)
    baseline = resample_minute_bars(
        bars,
        bar_size="15min",
        parent_snapshot_id="snapshot-1min",
    )
    changed = bars.copy()
    changed.loc[15, "close"] = 9_999.0

    after_change = resample_minute_bars(
        changed,
        bar_size="15min",
        parent_snapshot_id="snapshot-1min",
    )

    assert baseline.to_dict("records") == after_change.to_dict("records")


def test_resample_allows_a_complete_interval_to_finish_at_session_close() -> None:
    bars = _minute_bars(count=390)

    derived = resample_minute_bars(
        bars,
        bar_size="5min",
        parent_snapshot_id="snapshot-1min",
    )

    assert len(derived) == 78
    assert derived.loc[77, "available_at"] == pd.Timestamp("2026-07-02T20:00:00Z")
