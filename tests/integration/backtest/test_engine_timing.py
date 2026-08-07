from dataclasses import replace
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from us_intraday_lab.backtest.costs import COST_SCENARIOS
from us_intraday_lab.backtest.engine import (
    CALENDAR_ID,
    BacktestEngine,
    input_data_sha256,
)
from us_intraday_lab.contracts.backtests import BacktestJob, CostModelIds
from us_intraday_lab.contracts.strategies import StrategyDefinition
from us_intraday_lab.data.calendar import expected_minute_index
from us_intraday_lab.data.resample import resample_minute_bars
from us_intraday_lab.strategy.compiler import compile_strategy
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


def _golden_strategy() -> StrategyDefinition:
    return StrategyDefinition.model_validate(
        {
            "strategy_id": "golden-entry-v1",
            "dsl_version": "1.0.0",
            "symbols": ["SPY"],
            "signal_bar_size": "15min",
            "entry": {
                "indicator": "minutes_from_open",
                "op": "gte",
                "value": 15.0,
            },
            "exit": {
                "indicator": "minutes_from_open",
                "op": "gte",
                "value": 999.0,
            },
            "risk": {
                "stop_loss_bps": 10_000,
                "take_profit_bps": 10_000,
                "max_holding_minutes": 999,
                "cooldown_minutes": 1,
                "max_entries_per_session": 1,
                "sizing_preset": "equal_cash_conservative",
            },
            "order_type": "market",
        }
    )


def _golden_job(
    strategy: StrategyDefinition,
    *,
    closeout_buffer_minutes: int = 5,
    minute_bars: pd.DataFrame | None = None,
    signal_bars: pd.DataFrame | None = None,
) -> BacktestJob:
    compiled = compile_strategy(strategy)
    minute_bars = _full_session_minute_bars() if minute_bars is None else minute_bars
    signal_bars = _one_completed_signal_bar() if signal_bars is None else signal_bars
    return BacktestJob.create(
        schema_version="1.0.0",
        strategy_id=compiled.definition_fingerprint,
        dataset_id="synthetic-accepted-dataset",
        engine_id="event-engine-1.0.0",
        calendar_id=CALENDAR_ID,
        input_data_sha256=input_data_sha256(minute_bars, signal_bars),
        initial_cash=25_000.0,
        closeout_buffer_minutes=closeout_buffer_minutes,
        cost_model_ids=CostModelIds(
            optimistic=COST_SCENARIOS["optimistic"].model_id,
            base=COST_SCENARIOS["base"].model_id,
            stress=COST_SCENARIOS["stress"].model_id,
        ),
    )


def _full_session_minute_bars() -> pd.DataFrame:
    timestamps = expected_minute_index(SESSION_DATE)
    return pd.DataFrame(
        {
            "symbol": "SPY",
            "timestamp": timestamps,
            "open": 100.0,
            "high": 100.2,
            "low": 99.8,
            "close": 100.0,
            "volume": 10_000.0,
            "session_date": SESSION_DATE,
        }
    )


def _one_completed_signal_bar() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["SPY"],
            "available_at": [datetime(2026, 7, 2, 13, 45, tzinfo=UTC)],
            "open": [100.0],
            "high": [100.2],
            "low": [99.8],
            "close": [100.0],
            "volume": [150_000.0],
            "session_date": [SESSION_DATE],
        }
    )


def test_engine_golden_sequence_obeys_next_minute_and_finishes_flat() -> None:
    strategy = _golden_strategy()
    run = BacktestEngine(
        job=_golden_job(strategy),
        strategy=compile_strategy(strategy),
    ).run_scenario(
        minute_bars=_full_session_minute_bars(),
        signal_bars=_one_completed_signal_bar(),
        cost_scenario="base",
    )

    assert [event.event_type for event in run.events] == [
        "BAR_CLOSED_15M",
        "ENTRY_OPPORTUNITY",
        "SIGNAL_ENTER_LONG",
        "ORDER_INTENT_CREATED",
        "ORDER_ELIGIBLE",
        "ORDER_FILLED",
        "POSITION_OPENED",
        "SIGNAL_EXIT_LONG",
        "ORDER_INTENT_CREATED",
        "ORDER_FILLED",
        "POSITION_CLOSED",
        "SESSION_FINALIZED",
    ]
    opening_intent = run.intents[0]
    opening_fill = next(
        event
        for event in run.events
        if event.event_type == "ORDER_FILLED" and event.details["side"] == "buy"
    )
    assert opening_intent.signal_time < opening_intent.eligible_time
    assert opening_intent.eligible_time <= opening_fill.event_time
    assert run.final_positions == ()
    assert len(run.trades) == 1
    assert run.trades[0].forced
    assert run.events[-1].details["position_count"] == 0


def test_engine_rejects_job_strategy_identity_that_does_not_match_definition() -> None:
    strategy = _golden_strategy()
    job = BacktestJob.create(
        **{
            **_golden_job(strategy).model_dump(exclude={"job_id", "strategy_id"}),
            "strategy_id": "golden-entry-v1@sha256:" + "0" * 64,
        }
    )

    with pytest.raises(ValueError, match="strategy identity"):
        BacktestEngine(job=job, strategy=compile_strategy(strategy))


def test_engine_rejects_compiled_rules_replaced_under_original_fingerprint() -> None:
    definition = _golden_strategy()
    compiled = compile_strategy(definition)
    forged = replace(compiled, entry=compiled.exit)

    with pytest.raises(ValueError, match="compiled strategy content"):
        BacktestEngine(job=_golden_job(definition), strategy=forged)


def test_engine_rejects_input_frames_that_do_not_match_job_identity() -> None:
    strategy = _golden_strategy()
    changed_minutes = _full_session_minute_bars()
    changed_minutes.loc[1, "open"] = 777.0

    with pytest.raises(ValueError, match="input data"):
        BacktestEngine(
            job=_golden_job(strategy),
            strategy=compile_strategy(strategy),
        ).run_scenario(
            minute_bars=changed_minutes,
            signal_bars=_one_completed_signal_bar(),
            cost_scenario="base",
        )


def test_closeout_processes_boundary_eligible_entry_then_liquidates_on_official_minute() -> None:
    strategy = StrategyDefinition.model_validate(
        {**_golden_strategy().model_dump(mode="json"), "order_type": "limit"}
    )
    signal_bars = _one_completed_signal_bar().copy()
    signal_bars["available_at"] = datetime(2026, 7, 2, 19, 45, tzinfo=UTC)
    signal_bars[["open", "high", "low", "close"]] = [99.0, 99.2, 98.8, 99.0]
    minute_bars = _full_session_minute_bars()
    minute_bars.loc[
        minute_bars["timestamp"] == datetime(2026, 7, 2, 19, 54, tzinfo=UTC),
        "low",
    ] = 98.8
    compiled = compile_strategy(strategy)

    run = BacktestEngine(
        job=_golden_job(
            strategy,
            closeout_buffer_minutes=5,
            minute_bars=minute_bars,
            signal_bars=signal_bars,
        ),
        strategy=compiled,
    ).run_scenario(
        minute_bars=minute_bars,
        signal_bars=signal_bars,
        cost_scenario="base",
    )

    buy_fill = next(
        event
        for event in run.events
        if event.event_type == "ORDER_FILLED" and event.details["side"] == "buy"
    )
    forced_sell = next(trade for trade in run.trades if trade.forced)
    official_minutes = set(expected_minute_index(SESSION_DATE).to_pydatetime())

    assert buy_fill.event_time == datetime(2026, 7, 2, 19, 54, tzinfo=UTC)
    assert forced_sell.exit_time == datetime(2026, 7, 2, 19, 55, tzinfo=UTC)
    assert forced_sell.exit_time < datetime(2026, 7, 2, 20, 0, tzinfo=UTC)
    assert all(point.event_time in official_minutes for point in run.equity_curve)


def test_one_minute_closeout_buffer_fills_on_last_official_minute() -> None:
    strategy = _golden_strategy()
    compiled = compile_strategy(strategy)
    run = BacktestEngine(
        job=_golden_job(strategy, closeout_buffer_minutes=1),
        strategy=compiled,
    ).run_scenario(
        minute_bars=_full_session_minute_bars(),
        signal_bars=_one_completed_signal_bar(),
        cost_scenario="base",
    )

    assert run.trades[0].exit_time == datetime(2026, 7, 2, 19, 59, tzinfo=UTC)
    assert run.trades[0].exit_time < datetime(2026, 7, 2, 20, 0, tzinfo=UTC)


def test_max_entries_per_session_is_global_across_strategy_symbols() -> None:
    base = _golden_strategy().model_dump(mode="json")
    base["symbols"] = ["SPY", "QQQ", "IWM"]
    base["risk"]["max_entries_per_session"] = 1
    strategy = StrategyDefinition.model_validate(base)
    minute_bars = pd.concat(
        [_full_session_minute_bars().assign(symbol=symbol) for symbol in strategy.symbols],
        ignore_index=True,
    )
    signal_bars = pd.concat(
        [_one_completed_signal_bar().assign(symbol=symbol) for symbol in strategy.symbols],
        ignore_index=True,
    )

    run = BacktestEngine(
        job=_golden_job(strategy, minute_bars=minute_bars, signal_bars=signal_bars),
        strategy=compile_strategy(strategy),
    ).run_scenario(
        minute_bars=minute_bars,
        signal_bars=signal_bars,
        cost_scenario="base",
    )

    buy_fills = [
        event
        for event in run.events
        if event.event_type == "ORDER_FILLED" and event.details["side"] == "buy"
    ]
    assert len(buy_fills) == 1
