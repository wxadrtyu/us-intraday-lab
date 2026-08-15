from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from us_intraday_lab.dual_sleeve import DualSleeveParameters
from us_intraday_lab.research_shadow_alpaca import (
    AlpacaIexHistory,
    evaluate_alpaca_dual_sleeve_session,
)

NEW_YORK = ZoneInfo("America/New_York")


def _timestamp(session: date, minute: int) -> datetime:
    return datetime.combine(session, time(9, 30), NEW_YORK) + timedelta(minutes=minute)


def _bars() -> tuple[pd.DataFrame, tuple[str, ...], date]:
    universe = tuple(f"S{index:02d}" for index in range(51))
    target = date(2026, 8, 11)
    context = tuple(target - timedelta(days=index) for index in range(12, 1, -1))
    rows = []
    for session in context:
        for symbol in universe:
            for minute in (0, 30, 45, 46, 330):
                rows.append(
                    {
                        "symbol": symbol,
                        "timestamp": _timestamp(session, minute),
                        "open": 100.0,
                        "high": 100.1,
                        "low": 99.9,
                        "close": 100.0,
                        "volume": 100,
                    }
                )
        for minute in range(390):
            price = 100.0 + minute * 0.0001
            rows.append(
                {
                    "symbol": "SPY",
                    "timestamp": _timestamp(session, minute),
                    "open": price,
                    "high": price + 0.01,
                    "low": price - 0.01,
                    "close": price + 0.001,
                    "volume": 1000,
                }
            )
    for symbol in universe:
        for minute in range(390):
            is_winner = symbol == universe[0]
            close = 101.5 if is_winner and minute == 45 else 100.0
            high = 102.1 if is_winner and minute == 50 else max(100.2, close)
            low = 99.0 if is_winner and minute <= 45 else 99.8
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": _timestamp(target, minute),
                    "open": 100.0,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": 200 if is_winner and minute <= 45 else 100,
                }
            )
    for minute in range(390):
        price = 100.0
        if minute >= 30:
            price = 100.4
        if minute >= 45:
            price = 100.5
        if minute >= 300:
            price = 100.8
        rows.append(
            {
                "symbol": "SPY",
                "timestamp": _timestamp(target, minute),
                "open": price,
                "high": price + 0.01,
                "low": price - 0.01,
                "close": price,
                "volume": 1000,
            }
        )
    return pd.DataFrame(rows), universe, target


def test_alpaca_shadow_evaluation_is_long_only_exact_and_broker_free() -> None:
    bars, universe, target = _bars()
    parameters = DualSleeveParameters(0.005, 0.7, 0.003, 300)

    observed = evaluate_alpaca_dual_sleeve_session(
        bars,
        session_date=target,
        universe=universe,
        parameters=parameters,
        round_trip_cost=0.0009,
    )
    record = observed.as_record(parameters)

    assert observed.stock_signal
    assert observed.stock_symbol == universe[0]
    assert observed.spy_signal
    assert observed.stock_sleeve_return == pytest.approx(0.5 * (0.02 - 0.0009))
    assert observed.strategy_return > 0.0
    assert observed.target_spy_minutes == 390
    assert observed.target_minimum_stock_minutes == 390
    assert all("order" not in key.lower() for key in record)


def test_shadow_evaluation_supports_frozen_fifty_symbol_universe() -> None:
    bars, universe, target = _bars()
    reduced = universe[:-1]
    bars = bars.loc[~bars["symbol"].eq(universe[-1])].copy()

    observed = evaluate_alpaca_dual_sleeve_session(
        bars,
        session_date=target,
        universe=reduced,
        parameters=DualSleeveParameters(0.005, 0.7, 0.003, 300),
        round_trip_cost=0.0009,
    )
    record = observed.as_record(
        DualSleeveParameters(0.005, 0.7, 0.003, 300),
        provider="twelve_data",
        feed="minute",
    )

    assert observed.target_minimum_stock_minutes == 390
    assert record["provider"] == "twelve_data"
    assert record["feed"] == "minute"


def test_alpaca_shadow_history_requires_dedicated_paper_data_credentials() -> None:
    with pytest.raises(RuntimeError, match="MARKET_DATA_CREDENTIAL_MISSING"):
        AlpacaIexHistory.from_environment(environ={})
