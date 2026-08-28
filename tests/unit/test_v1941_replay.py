from __future__ import annotations

from datetime import date, timedelta
from importlib import import_module

import pandas as pd
import pytest

from us_intraday_lab.paper.v449 import SleeveSignal
from us_intraday_lab.v45_research_shadow import SYMBOLS
from us_intraday_lab.v1941_research_shadow import bar_time

module = import_module("replay_v1941_sessions")
SESSION = date(2026, 8, 27)


def frame():
    return pd.DataFrame(
        [
            {
                "symbol": symbol,
                "timestamp": bar_time(SESSION, 0) + timedelta(minutes=m),
                "open": 100.0 if m < 300 else 105.0,
                "close": 100.0,
                "high": 106.0,
                "low": 99.0,
                "volume": 10,
            }
            for symbol in SYMBOLS
            for m in range(390)
        ]
    )


def signal(bars, *, session_date, decision_bar):
    assert bars.timestamp.max() < bar_time(session_date, decision_bar + 1)
    return (SleeveSignal("anchor", "SOXL", 23, 72, 1.0, 1.0),) if decision_bar == 23 else ()


def test_replay_explicitly_not_prospective_and_has_no_fabricated_receipt(monkeypatch):
    monkeypatch.setattr(module, "v1254_signals_at", signal)
    result = module.replay(frame(), SESSION, bar_time(SESSION, 78))
    assert result["status"] == "COMPLETE_DIAGNOSTIC"
    assert result["prospective"] is False
    assert result["actual_orders"] == 0
    assert result["order_route"] == "FORBIDDEN"
    assert "receipt_next_minute_9bp" not in result["scenarios"]
    assert "receipt_entry_minute" not in result["signals"][0]
    assert result["scenarios"]["9bp"]["v1941_return"] == pytest.approx((0.05 - 0.0009) * 0.45)


def test_pending_exit_never_uses_future_prices_or_reports_zero(monkeypatch):
    monkeypatch.setattr(module, "v1254_signals_at", signal)
    result = module.replay(frame(), SESSION, bar_time(SESSION, 40))
    assert result["status"] == "INCOMPLETE_DIAGNOSTIC"
    for scenario in result["scenarios"].values():
        assert scenario["v1941_return"] is None
        assert scenario["incomplete"][0]["reason"] == "PENDING_EXIT"


def test_missing_exact_entry_is_not_zero_profit(monkeypatch):
    monkeypatch.setattr(module, "v1254_signals_at", signal)
    bars = frame()
    bars = bars.loc[~((bars.symbol == "SOXL") & (bars.timestamp == bar_time(SESSION, 24)))]
    result = module.replay(bars, SESSION, bar_time(SESSION, 78))
    assert result["scenarios"]["9bp"]["v1941_return"] is None
    assert result["scenarios"]["9bp"]["incomplete"][0]["reason"] == "MISSING_EXACT_PRICE"


def test_missing_target_cannot_be_reported_as_no_signal(monkeypatch):
    monkeypatch.setattr(module, "v1254_signals_at", signal)
    result = module.replay(
        frame().loc[lambda f: f.symbol != "SOXL"], SESSION, bar_time(SESSION, 78)
    )
    assert result["status"] == "INCOMPLETE_DIAGNOSTIC"
    assert all(d["status"] == "INCOMPLETE_INPUT" for d in result["decisions"])
    assert result["scenarios"]["9bp"]["v1941_return"] is None
