from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from us_intraday_lab.backtest.costs import COST_SCENARIOS
from us_intraday_lab.contracts.backtests import BacktestJob, CostModelIds
from us_intraday_lab.contracts.strategies import StrategyDefinition
from us_intraday_lab.long_horizon.engine import (
    FIVE_MINUTE_ENGINE_ID,
    FiveMinuteBacktestEngine,
    _feature_frame,
    five_minute_input_sha256,
)
from us_intraday_lab.strategy.compiler import compile_strategy


def _strategy(
    *,
    entry_minute: int = 30,
    symbols: tuple[str, str] = ("AAPL", "QQQ"),
    sizing_preset: str = "equal_cash_conservative",
) -> StrategyDefinition:
    return StrategyDefinition.model_validate(
        {
            "strategy_id": "five-minute-engine-test",
            "dsl_version": "1.0.0",
            "symbols": list(symbols),
            "signal_bar_size": "5min",
            "entry": {
                "all": [
                    {
                        "indicator": "minutes_from_open",
                        "op": "gte",
                        "value": entry_minute,
                    }
                ]
            },
            "exit": {
                "any": [
                    {"indicator": "minutes_from_open", "op": "gt", "value": 1_000}
                ]
            },
            "risk": {
                "stop_loss_bps": 100,
                "take_profit_bps": 200,
                "max_holding_minutes": 90,
                "cooldown_minutes": 30,
                "max_entries_per_session": 1,
                "sizing_preset": sizing_preset,
            },
            "order_type": "market",
        }
    )


def _bars(
    *, ambiguous: bool = False, symbols: tuple[str, str] = ("AAPL", "QQQ")
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    session = date(2025, 1, 2)
    available = datetime(2025, 1, 2, 14, 35, tzinfo=UTC)
    for symbol in symbols:
        for index in range(8):
            price = 100.0
            if symbol == "AAPL" and index == 6:
                price = 101.0
            high = price + 0.2
            low = price - 0.2
            if ambiguous and symbol == "AAPL" and index == 7:
                price = 100.0
                high = 103.0
                low = 98.0
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": available + timedelta(minutes=5 * index),
                    "available_at": available + timedelta(minutes=5 * index),
                    "open": price,
                    "high": high,
                    "low": low,
                    "close": price,
                    "volume": 1_000.0,
                    "session_date": session,
                }
            )
    return pd.DataFrame(rows)


def _run(
    *,
    ambiguous: bool = False,
    entry_minute: int = 30,
    symbols: tuple[str, str] = ("AAPL", "QQQ"),
    sizing_preset: str = "equal_cash_conservative",
):
    bars = _bars(ambiguous=ambiguous, symbols=symbols)
    compiled = compile_strategy(
        _strategy(
            entry_minute=entry_minute,
            symbols=symbols,
            sizing_preset=sizing_preset,
        )
    )
    job = BacktestJob.create(
        schema_version="1.0.0",
        strategy_id=compiled.definition_fingerprint,
        dataset_id="fixture-five-minute",
        engine_id=FIVE_MINUTE_ENGINE_ID,
        calendar_id="XNYS@fixture",
        input_data_sha256=five_minute_input_sha256(bars),
        initial_cash=100_000.0,
        closeout_buffer_minutes=5,
        cost_model_ids=CostModelIds(
            optimistic=COST_SCENARIOS["optimistic"].model_id,
            base=COST_SCENARIOS["base"].model_id,
            stress=COST_SCENARIOS["stress"].model_id,
        ),
    )
    return FiveMinuteBacktestEngine(job=job, strategy=compiled).run(bars_5m=bars)


def test_entry_fills_at_next_five_minute_open() -> None:
    run = _run().scenarios["base"]
    aapl = next(trade for trade in run.trades if trade.symbol == "AAPL")

    assert aapl.entry_time == datetime(2025, 1, 2, 15, 5, tzinfo=UTC)
    assert aapl.entry_price == 101.0


def test_leveraged_sizing_caps_each_symbol_at_twenty_five_percent() -> None:
    run = _run(sizing_preset="equal_cash_leveraged_25pct").scenarios["base"]

    assert {trade.quantity for trade in run.trades} == {250}


def test_same_bar_stop_and_target_uses_adverse_first() -> None:
    run = _run(ambiguous=True, entry_minute=25).scenarios["base"]
    aapl = next(trade for trade in run.trades if trade.symbol == "AAPL")

    assert aapl.exit_price == pytest.approx(99.0)
    assert aapl.net_pnl < 0


def test_feature_bar_cannot_trade_before_available_at() -> None:
    run = _run().scenarios["base"]

    assert all(intent.signal_time >= datetime(2025, 1, 2, 15, 0, tzinfo=UTC) for intent in run.intents)
    assert all(intent.eligible_time == intent.signal_time + timedelta(minutes=5) for intent in run.intents)


def test_engine_retains_observable_entry_candidates_and_matching_opportunities() -> None:
    run = _run().scenarios["base"]
    candidates = [event for event in run.events if event.event_type == "ENTRY_CANDIDATE"]
    opportunities = [event for event in run.events if event.event_type == "ENTRY_OPPORTUNITY"]

    assert candidates
    assert opportunities
    assert len(candidates) > len(opportunities)
    assert all(event.event_time >= datetime(2025, 1, 2, 15, tzinfo=UTC) for event in opportunities)


def test_engine_accepts_the_closed_spy_iwm_scope() -> None:
    run = _run(symbols=("SPY", "IWM")).scenarios["base"]

    assert {trade.symbol for trade in run.trades} == {"SPY", "IWM"}


def test_cross_session_features_use_only_completed_prior_sessions() -> None:
    rows: list[dict[str, object]] = []
    sessions = (date(2025, 1, 2), date(2025, 1, 3), date(2025, 1, 6))
    closes = {sessions[0]: 100.0, sessions[1]: 90.0, sessions[2]: 80.0}
    for session in sessions:
        start = datetime.combine(session, datetime.min.time(), tzinfo=UTC) + timedelta(
            hours=14, minutes=35
        )
        for symbol, scale in (("SPY", 1.0), ("IWM", 2.0)):
            for index in range(2):
                price = closes[session] * scale
                rows.append(
                    {
                        "symbol": symbol,
                        "timestamp": start + timedelta(minutes=5 * index),
                        "available_at": start + timedelta(minutes=5 * index),
                        "open": closes[session] * scale,
                        "high": price + 0.1,
                        "low": price - 0.1,
                        "close": price,
                        "volume": 1_000.0,
                        "session_date": session,
                    }
                )
    features = _feature_frame(pd.DataFrame(rows))
    current = features.loc[
        (features["session_date"] == sessions[2])
        & (features["symbol"] == "SPY")
    ].reset_index(drop=True)

    assert current.loc[0, "prior_session_return"] == pytest.approx(-0.1)
    assert current.loc[0, "return_from_open"] == pytest.approx(0.0)
    assert current.loc[0, "peer_return_from_open"] == pytest.approx(0.0)
    assert current.loc[0, "relative_return_from_open"] == pytest.approx(0.0)
    assert current.loc[0, "peer_prior_session_return"] == pytest.approx(-0.1)
    assert current.loc[0, "pair_prior_session_return_min"] == pytest.approx(-0.1)


def test_trailing_session_features_exclude_the_current_session() -> None:
    rows: list[dict[str, object]] = []
    sessions = (
        date(2025, 1, 13),
        date(2025, 1, 14),
        date(2025, 1, 15),
        date(2025, 1, 16),
        date(2025, 1, 17),
        date(2025, 1, 21),
        date(2025, 1, 22),
    )
    closes = (100.0, 102.0, 104.0, 106.0, 108.0, 110.0, 500.0)
    for session, close in zip(sessions, closes, strict=True):
        start = datetime.combine(session, datetime.min.time(), tzinfo=UTC) + timedelta(
            hours=14, minutes=35
        )
        for symbol, scale in (("SPY", 1.0), ("IWM", 2.0)):
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": start,
                    "available_at": start,
                    "open": close * scale,
                    "high": close * scale + 0.1,
                    "low": close * scale - 0.1,
                    "close": close * scale,
                    "volume": 1_000.0,
                    "session_date": session,
                }
            )
    features = _feature_frame(pd.DataFrame(rows))
    current = features.loc[
        (features["session_date"] == sessions[-1])
        & (features["symbol"] == "SPY")
    ].reset_index(drop=True)

    expected = closes[-2] / closes[0] - 1.0
    expected_three = closes[-2] / closes[-5] - 1.0
    assert current.loc[0, "trailing_session_return_3"] == pytest.approx(expected_three)
    assert current.loc[0, "trailing_session_return_5"] == pytest.approx(expected)
    assert current.loc[0, "peer_trailing_session_return_5"] == pytest.approx(expected)
    assert current.loc[0, "is_tqqq"] == 0.0
    assert current.loc[0, "is_soxl"] == 0.0
