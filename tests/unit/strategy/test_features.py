from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from us_intraday_lab.strategy.features import (
    FEATURE_COLUMNS,
    FEATURE_SET_VERSION,
    compute_feature_frame,
    visible_feature_frame,
)
from us_intraday_lab.strategy.runtime import (
    EngineStateError,
    RuntimeKey,
    RuntimePhase,
    StrategyRuntime,
)

SESSION_DATE = date(2026, 7, 2)


def _derived_bars(count: int = 4) -> pd.DataFrame:
    available_at = pd.date_range(
        "2026-07-02T13:45:00Z",
        periods=count,
        freq="15min",
        tz="UTC",
    )
    return pd.DataFrame(
        {
            "symbol": "SPY",
            "available_at": available_at,
            "open": [100.0 + index for index in range(count)],
            "high": [101.5 + index for index in range(count)],
            "low": [99.5 + index for index in range(count)],
            "close": [101.0 + index for index in range(count)],
            "volume": [1_000.0 + 100.0 * index for index in range(count)],
            "session_date": SESSION_DATE,
        }
    )


def test_feature_frame_has_versioned_schema_and_completed_bar_times() -> None:
    features = compute_feature_frame(_derived_bars())

    assert tuple(features.columns) == FEATURE_COLUMNS
    assert features["feature_set_version"].unique().tolist() == [FEATURE_SET_VERSION]
    assert features.loc[0, "bar_start"] == pd.Timestamp("2026-07-02T13:30:00Z")
    assert features.loc[0, "available_at"] == pd.Timestamp("2026-07-02T13:45:00Z")
    assert features.loc[0, "minutes_from_open"] == 15


def test_rolling_feature_warmups_remain_null_without_future_backfill() -> None:
    features = compute_feature_frame(_derived_bars())

    assert pd.isna(features.loc[0, "return_1"])
    assert pd.isna(features.loc[2, "return_3"])
    assert features.loc[3, "return_3"] == (104.0 / 101.0) - 1.0
    assert features.loc[:3, "ema_spread"].isna().all()
    assert features.loc[:3, "rsi"].isna().all()
    assert features.loc[:3, "atr_bps"].isna().all()
    assert features.loc[:3, "volume_ratio"].isna().all()


def test_feature_visibility_excludes_rows_after_aware_utc_clock() -> None:
    features = compute_feature_frame(_derived_bars(count=2))

    visible = visible_feature_frame(
        features,
        clock_time=pd.Timestamp("2026-07-02T13:45:00Z"),
    )

    assert len(visible) == 1
    assert visible.loc[0, "available_at"] == pd.Timestamp("2026-07-02T13:45:00Z")


def test_feature_frame_is_deterministic_for_unsorted_input() -> None:
    bars = _derived_bars()

    first = compute_feature_frame(bars.sample(frac=1.0, random_state=1))
    second = compute_feature_frame(bars.sample(frac=1.0, random_state=2))

    pd.testing.assert_frame_equal(first, second)


def _time(hour: int, minute: int) -> datetime:
    return datetime(2026, 7, 2, hour, minute, tzinfo=UTC)


def test_runtime_state_is_isolated_by_strategy_symbol_and_session() -> None:
    runtime = StrategyRuntime()
    active = RuntimeKey("momentum", "SPY", SESSION_DATE)
    other_strategy = RuntimeKey("reversion", "SPY", SESSION_DATE)
    other_symbol = RuntimeKey("momentum", "QQQ", SESSION_DATE)
    next_session = RuntimeKey("momentum", "SPY", date(2026, 7, 6))

    runtime.record_signal(active, signal="ENTER_LONG", event_time=_time(13, 45))
    runtime.transition(active, RuntimePhase.ENTRY_PENDING, event_time=_time(13, 45))
    runtime.record_opening_fill(active, event_time=_time(13, 46))

    assert runtime.state_for(active).entries == 1
    assert runtime.state_for(active).last_signal == "ENTER_LONG"
    assert runtime.holding_minutes(active, clock_time=_time(14, 1)) == 15
    for untouched in (other_strategy, other_symbol):
        assert runtime.state_for(untouched).phase is RuntimePhase.FLAT
        assert runtime.state_for(untouched).entries == 0
        assert runtime.state_for(untouched).last_signal is None
        assert runtime.holding_minutes(untouched, clock_time=_time(14, 1)) is None
    assert runtime.state_for(next_session).phase is RuntimePhase.FLAT
    assert runtime.state_for(next_session).entries == 0
    assert runtime.state_for(next_session).last_signal is None
    assert (
        runtime.holding_minutes(
            next_session,
            clock_time=datetime(2026, 7, 6, 14, 1, tzinfo=UTC),
        )
        is None
    )


def test_rejected_opening_order_does_not_count_as_entry_but_fill_does() -> None:
    runtime = StrategyRuntime()
    key = RuntimeKey("momentum", "SPY", SESSION_DATE)
    runtime.transition(key, RuntimePhase.ENTRY_PENDING, event_time=_time(13, 45))

    runtime.record_order_rejected(key, event_time=_time(13, 46))

    assert runtime.state_for(key).phase is RuntimePhase.FLAT
    assert runtime.state_for(key).entries == 0

    runtime.transition(key, RuntimePhase.ENTRY_PENDING, event_time=_time(14, 0))
    runtime.record_opening_fill(key, event_time=_time(14, 1))

    assert runtime.state_for(key).phase is RuntimePhase.LONG
    assert runtime.state_for(key).entries == 1


def test_exit_fill_starts_session_local_cooldown() -> None:
    runtime = StrategyRuntime()
    key = RuntimeKey("momentum", "SPY", SESSION_DATE)
    other = RuntimeKey("momentum", "QQQ", SESSION_DATE)
    runtime.transition(key, RuntimePhase.ENTRY_PENDING, event_time=_time(13, 45))
    runtime.record_opening_fill(key, event_time=_time(13, 46))
    runtime.transition(key, RuntimePhase.EXIT_PENDING, event_time=_time(14, 0))

    runtime.record_exit_fill(
        key,
        event_time=_time(14, 1),
        cooldown_minutes=30,
    )

    assert runtime.state_for(key).phase is RuntimePhase.COOLDOWN
    assert runtime.state_for(key).cooldown_until == _time(14, 31)
    assert runtime.cooldown_active(key, clock_time=_time(14, 30))
    assert not runtime.cooldown_active(key, clock_time=_time(14, 31))
    assert runtime.state_for(other).cooldown_until is None


def test_illegal_transition_raises_typed_error_and_appends_audit_event() -> None:
    runtime = StrategyRuntime()
    key = RuntimeKey("momentum", "SPY", SESSION_DATE)

    with pytest.raises(EngineStateError) as exc_info:
        runtime.transition(key, RuntimePhase.LONG, event_time=_time(13, 45))

    assert exc_info.value.code == "ILLEGAL_STATE_TRANSITION"
    assert runtime.state_for(key).phase is RuntimePhase.FLAT
    event = runtime.audit_events[-1]
    assert event.event_type == "state_transition"
    assert event.outcome == "rejected"
    assert event.from_phase is RuntimePhase.FLAT
    assert event.to_phase is RuntimePhase.LONG


def test_session_close_is_terminal_and_new_session_starts_reset() -> None:
    runtime = StrategyRuntime()
    key = RuntimeKey("momentum", "SPY", SESSION_DATE)
    next_session = RuntimeKey("momentum", "SPY", date(2026, 7, 6))

    runtime.close_session(key, event_time=_time(20, 0))

    assert runtime.state_for(key).phase is RuntimePhase.SESSION_CLOSED
    assert runtime.state_for(next_session).phase is RuntimePhase.FLAT
    assert runtime.state_for(next_session).entries == 0
    with pytest.raises(EngineStateError):
        runtime.transition(
            key,
            RuntimePhase.FLAT,
            event_time=_time(20, 0) + timedelta(seconds=1),
        )
