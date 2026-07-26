from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from us_intraday_lab.strategy.features import (
    FEATURE_COLUMNS,
    FEATURE_SET_VERSION,
    compute_feature_frame,
    visible_feature_frame,
)
from us_intraday_lab.strategy.runtime import (
    RuntimeKey,
    RuntimePhase,
    RuntimeState,
    RuntimeTransitionError,
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


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("symbol", None),
        ("symbol", ""),
        ("symbol", "   "),
        ("session_date", None),
        ("session_date", "2026-07-02"),
        ("session_date", datetime(2026, 7, 2, tzinfo=UTC)),
    ],
)
def test_feature_frame_rejects_invalid_group_keys_before_grouping(
    column: str,
    value: object,
) -> None:
    bars = _derived_bars(count=2)
    bars[column] = bars[column].astype("object")
    bars.at[1, column] = value

    with pytest.raises((TypeError, ValueError), match=column):
        compute_feature_frame(bars)


def test_feature_frame_rejects_non_utc_available_at() -> None:
    bars = _derived_bars(count=2)
    bars["available_at"] = bars["available_at"].astype("object")
    bars.at[1, "available_at"] = pd.Timestamp(
        "2026-07-02 10:00:00",
        tz="America/New_York",
    )

    with pytest.raises(ValueError, match="available_at must be timezone-aware UTC"):
        compute_feature_frame(bars)


def test_feature_frame_rejects_bar_off_completed_fifteen_minute_boundary() -> None:
    bars = _derived_bars(count=2)
    bars.at[1, "available_at"] = pd.Timestamp("2026-07-02T14:01:00Z")

    with pytest.raises(ValueError, match="completed 15-minute XNYS boundary"):
        compute_feature_frame(bars)


def test_feature_frame_validates_optional_bar_start_as_aware_utc_and_exact() -> None:
    bars = _derived_bars(count=2)
    bars["bar_start"] = bars["available_at"] - pd.Timedelta(minutes=15)
    bars["bar_start"] = bars["bar_start"].astype("object")
    bars.at[1, "bar_start"] = pd.Timestamp(
        "2026-07-02 09:45:00",
        tz="America/New_York",
    )

    with pytest.raises(ValueError, match="bar_start must be timezone-aware UTC"):
        compute_feature_frame(bars)

    bars.at[1, "bar_start"] = pd.Timestamp("2026-07-02T13:44:00Z")
    with pytest.raises(ValueError, match="bar_start must equal available_at minus 15 minutes"):
        compute_feature_frame(bars)


def _flat_zero_volume_bars(count: int = 20) -> pd.DataFrame:
    bars = _derived_bars(count=count)
    bars[["open", "high", "low", "close"]] = 100.0
    bars["volume"] = 0.0
    return bars


def test_zero_volume_and_flat_range_follow_explicit_null_and_neutral_policy() -> None:
    features = compute_feature_frame(_flat_zero_volume_bars())
    last = features.iloc[-1]

    assert pd.isna(last["volume_ratio"])
    assert pd.isna(last["vwap_distance_bps"])
    assert last["range_position"] == 0.5
    assert last["rsi"] == 50.0


def test_feature_outputs_never_expose_positive_or_negative_infinity() -> None:
    bars = _flat_zero_volume_bars()
    bars.loc[18, ["open", "high", "low", "close"]] = 0.0
    bars.loc[19, ["open", "high", "low", "close"]] = [0.0, 2.0, 0.0, 1.0]

    features = compute_feature_frame(bars)
    numeric = features.loc[
        :,
        [
            "return_1",
            "return_3",
            "ema_spread",
            "rsi",
            "atr_bps",
            "volume_ratio",
            "vwap_distance_bps",
            "range_position",
        ],
    ].to_numpy(dtype="float64")

    assert not np.isinf(numeric).any()
    assert pd.isna(features.loc[19, "return_1"])


def test_feature_set_v1_golden_values_lock_every_formula() -> None:
    bars = _derived_bars(count=20)
    indexes = np.arange(20, dtype="float64")
    bars["open"] = 99.5 + indexes
    bars["high"] = 101.0 + indexes
    bars["low"] = 99.0 + indexes
    bars["close"] = 100.0 + indexes
    bars["volume"] = 100.0 * (indexes + 1.0)

    last = compute_feature_frame(bars).iloc[-1]

    assert last["feature_set_version"] == "15m-v1.0.0"
    assert last["return_1"] == pytest.approx(119.0 / 118.0 - 1.0)
    assert last["return_3"] == pytest.approx(119.0 / 116.0 - 1.0)
    assert last["ema_spread"] == pytest.approx(0.021383864042765932)
    assert last["rsi"] == 100.0
    assert last["atr_bps"] == pytest.approx(2.0 / 119.0 * 10_000.0)
    assert last["volume_ratio"] == pytest.approx(2_000.0 / 1_050.0)
    assert last["vwap_distance_bps"] == pytest.approx((119.0 / (338.0 / 3.0) - 1.0) * 10_000.0)
    assert last["range_position"] == 0.5
    assert last["minutes_from_open"] == 300


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
    runtime.mark_entry_filled(active, event_time=_time(13, 46))

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
    runtime.mark_entry_filled(key, event_time=_time(14, 1))

    assert runtime.state_for(key).phase is RuntimePhase.LONG
    assert runtime.state_for(key).entries == 1


def test_exit_fill_starts_session_local_cooldown() -> None:
    runtime = StrategyRuntime()
    key = RuntimeKey("momentum", "SPY", SESSION_DATE)
    other = RuntimeKey("momentum", "QQQ", SESSION_DATE)
    runtime.transition(key, RuntimePhase.ENTRY_PENDING, event_time=_time(13, 45))
    runtime.mark_entry_filled(key, event_time=_time(13, 46))
    runtime.transition(key, RuntimePhase.EXIT_PENDING, event_time=_time(14, 0))

    runtime.mark_exit_filled(
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

    with pytest.raises(RuntimeTransitionError) as exc_info:
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
    with pytest.raises(RuntimeTransitionError):
        runtime.transition(
            key,
            RuntimePhase.FLAT,
            event_time=_time(20, 0) + timedelta(seconds=1),
        )


def test_public_transition_cannot_bypass_entry_fill_bookkeeping() -> None:
    runtime = StrategyRuntime()
    key = RuntimeKey("momentum", "SPY", SESSION_DATE)
    runtime.transition(key, RuntimePhase.ENTRY_PENDING, event_time=_time(13, 45))

    with pytest.raises(RuntimeTransitionError):
        runtime.transition(key, RuntimePhase.LONG, event_time=_time(13, 46))

    assert runtime.state_for(key).phase is RuntimePhase.ENTRY_PENDING
    assert runtime.state_for(key).entries == 0
    assert runtime.state_for(key).opened_at is None
    assert runtime.audit_events[-1].outcome == "rejected"


def test_public_transition_cannot_bypass_exit_fill_bookkeeping() -> None:
    runtime = StrategyRuntime()
    key = RuntimeKey("momentum", "SPY", SESSION_DATE)
    runtime.transition(key, RuntimePhase.ENTRY_PENDING, event_time=_time(13, 45))
    runtime.mark_entry_filled(key, event_time=_time(13, 46))
    runtime.transition(key, RuntimePhase.EXIT_PENDING, event_time=_time(14, 0))

    with pytest.raises(RuntimeTransitionError):
        runtime.transition(key, RuntimePhase.COOLDOWN, event_time=_time(14, 1))

    assert runtime.state_for(key).phase is RuntimePhase.EXIT_PENDING
    assert runtime.state_for(key).opened_at == _time(13, 46)
    assert runtime.state_for(key).cooldown_until is None
    assert runtime.audit_events[-1].outcome == "rejected"


@pytest.mark.parametrize(
    "invalid",
    [
        {"phase": RuntimePhase.LONG},
        {"phase": RuntimePhase.EXIT_PENDING, "entries": 1},
        {"phase": RuntimePhase.COOLDOWN},
        {
            "phase": RuntimePhase.LONG,
            "entries": 1,
            "opened_at": _time(13, 46).replace(tzinfo=None),
        },
        {
            "phase": RuntimePhase.COOLDOWN,
            "cooldown_until": _time(14, 31).replace(tzinfo=None),
        },
        {
            "last_signal": "ENTER_LONG",
            "last_signal_at": _time(13, 45).replace(tzinfo=None),
        },
    ],
)
def test_runtime_snapshots_cannot_represent_incomplete_phase_bookkeeping(
    invalid: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="runtime state invariant"):
        RuntimeState(**invalid)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "operation",
    [
        lambda runtime, key: runtime.record_signal(
            key,
            signal="ENTER_LONG",
            event_time=_time(20, 0) + timedelta(seconds=1),
        ),
        lambda runtime, key: runtime.transition(
            key,
            RuntimePhase.FLAT,
            event_time=_time(20, 0) + timedelta(seconds=1),
        ),
        lambda runtime, key: runtime.record_order_rejected(
            key,
            event_time=_time(20, 0) + timedelta(seconds=1),
        ),
        lambda runtime, key: runtime.mark_entry_filled(
            key,
            event_time=_time(20, 0) + timedelta(seconds=1),
        ),
        lambda runtime, key: runtime.mark_exit_filled(
            key,
            event_time=_time(20, 0) + timedelta(seconds=1),
            cooldown_minutes=30,
        ),
        lambda runtime, key: runtime.complete_cooldown(
            key,
            event_time=_time(20, 0) + timedelta(seconds=1),
        ),
        lambda runtime, key: runtime.close_session(
            key,
            event_time=_time(20, 0) + timedelta(seconds=1),
        ),
    ],
)
def test_session_closed_rejects_every_public_mutation_with_audit(
    operation: Callable[[StrategyRuntime, RuntimeKey], None],
) -> None:
    runtime = StrategyRuntime()
    key = RuntimeKey("momentum", "SPY", SESSION_DATE)
    runtime.close_session(key, event_time=_time(20, 0))
    before = runtime.state_for(key)
    audit_count = len(runtime.audit_events)

    with pytest.raises(RuntimeTransitionError):
        operation(runtime, key)

    assert runtime.state_for(key) == before
    assert len(runtime.audit_events) == audit_count + 1
    assert runtime.audit_events[-1].outcome == "rejected"
    assert runtime.audit_events[-1].from_phase is RuntimePhase.SESSION_CLOSED
