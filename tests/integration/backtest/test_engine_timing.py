from datetime import date

import pandas as pd

from us_intraday_lab.data.resample import resample_minute_bars
from us_intraday_lab.strategy.features import (
    compute_feature_frame,
)
from us_intraday_lab.strategy.runtime import StrategyRuntime

SESSION_DATE = date(2026, 7, 2)
SIGNAL_TIME = pd.Timestamp("2026-07-02 09:45:00", tz="America/New_York")


def _minute_bars() -> pd.DataFrame:
    timestamps = pd.date_range(
        "2026-07-02 09:30:00",
        periods=30,
        freq="min",
        tz="America/New_York",
    ).tz_convert("UTC")
    indexes = list(range(len(timestamps)))
    return pd.DataFrame(
        {
            "symbol": "SPY",
            "timestamp": timestamps,
            "open": [100.0 + index / 10 for index in indexes],
            "high": [100.2 + index / 10 for index in indexes],
            "low": [99.8 + index / 10 for index in indexes],
            "close": [100.1 + index / 10 for index in indexes],
            "volume": [1_000.0 + index for index in indexes],
            "session_date": SESSION_DATE,
        }
    )


def _features_visible_at_signal_time(minute_bars: pd.DataFrame) -> pd.DataFrame:
    completed_bars = resample_minute_bars(
        minute_bars,
        bar_size="15min",
        parent_snapshot_id="snapshot-1min",
    )
    feature_frame = compute_feature_frame(completed_bars)
    runtime = StrategyRuntime()
    return runtime.visible_features(feature_frame, clock_time=SIGNAL_TIME)


def test_0945_runtime_exposes_only_the_completed_0930_bar() -> None:
    visible = _features_visible_at_signal_time(_minute_bars())

    assert len(visible) == 1
    assert visible.loc[0, "bar_start"] == pd.Timestamp("2026-07-02T13:30:00Z")
    assert visible.loc[0, "available_at"] == pd.Timestamp("2026-07-02T13:45:00Z")


def test_0945_feature_vector_is_unchanged_by_inputs_at_or_after_0945() -> None:
    bars = _minute_bars()
    baseline = _features_visible_at_signal_time(bars)
    changed = bars.copy()
    future = changed["timestamp"] >= SIGNAL_TIME.tz_convert("UTC")
    changed.loc[future, ["open", "high", "low", "close", "volume"]] = [
        9_000.0,
        10_000.0,
        8_000.0,
        9_999.0,
        9_999_999.0,
    ]

    after_future_change = _features_visible_at_signal_time(changed)

    pd.testing.assert_frame_equal(baseline, after_future_change)
