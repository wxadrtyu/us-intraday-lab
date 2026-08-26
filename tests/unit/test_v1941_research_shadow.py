from __future__ import annotations

import ast
import importlib
import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from us_intraday_lab.v45_research_shadow import SYMBOLS
from us_intraday_lab.v1941_research_shadow import (
    CANDIDATE_ID,
    LABELS,
    MEANS,
    SCALES,
    THRESHOLD,
    ShadowLedger,
    bar_time,
    frozen_state,
    theoretical_results,
    through_bar,
)

SESSION = date(2026, 8, 26)


def bars(change=0.0):
    return pd.DataFrame(
        [
            {
                "symbol": s,
                "timestamp": bar_time(SESSION, 0) + timedelta(minutes=m),
                "open": 100.0,
                "high": 110.0,
                "low": 90.0,
                "close": 100.0 * (1 + change),
                "volume": 10,
            }
            for s in SYMBOLS
            for m in range(90)
        ]
    )


def test_frozen_definition_matches_research_artifact():
    path = Path(__file__).parents[2] / "research/results/2026-08-26-v1865-v1965-risk-overlay.json"
    candidate = json.loads(path.read_text())["retained_research_candidate"]
    assert candidate["candidate_id"] == CANDIDATE_ID
    assert candidate["model"]["mean"] == MEANS
    assert candidate["model"]["scale"] == SCALES
    assert candidate["definition"]["state_threshold"] == THRESHOLD
    assert candidate["definition"]["policy"] == "all_half_bad"
    assert candidate["definition"]["gross_budget_cap"] == 0.9


@pytest.mark.parametrize(("change", "expected"), [(0.0, 0.45), (0.05, 0.9)])
def test_state_policy_and_future_invariance(change, expected):
    frame = bars(change)
    first = frozen_state(frame, SESSION)
    future = frame.copy()
    future.timestamp += timedelta(minutes=90)
    future.close = 1e9
    assert frozen_state(pd.concat([frame, future]), SESSION) == first
    assert first["budget_multiplier"] == expected
    assert first["available_sectors"] == 11
    assert len(through_bar(pd.concat([frame, future]), SESSION, 17)) == len(frame)


def test_missing_spy_boundary_is_cash_not_filled():
    frame = bars()
    frame = frame.loc[~((frame.symbol == "SPY") & (frame.timestamp == bar_time(SESSION, 0)))]
    state = frozen_state(frame, SESSION)
    assert not state["state_valid"]
    assert state["budget_multiplier"] == 0
    assert state["score"] is None


def test_missing_sector_uses_frozen_denominator_eleven():
    state = frozen_state(bars(0.05).loc[lambda f: f.symbol != "XLB"], SESSION)
    assert state["available_sectors"] == 10
    assert state["factors"]["sector_breadth"] == 10 / 11


def test_ledger_is_append_only_and_cannot_override_forbidden_route(tmp_path):
    ledger = ShadowLedger(tmp_path / "events.sqlite3")
    assert ledger.append("one", "STATE", {"order_route": "ALLOW"})
    assert not ledger.append("one", "STATE", {"changed": True})
    assert ledger.get("one")["order_route"] == "FORBIDDEN"
    for statement in ("DELETE FROM events", "UPDATE events SET event_type='OTHER'"):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            ledger.connection.execute(statement)


def test_theoretical_cost_delay_receipt_and_missing_prices():
    signal = {
        "symbol": "SOXL",
        "sleeve": "anchor",
        "decision_bar": 23,
        "exit_bar": 72,
        "weight": 1.0,
        "exposure": 1.0,
        "receipt_entry_minute": 121,
    }
    frame = pd.DataFrame(
        [
            {"symbol": "SOXL", "timestamp": bar_time(SESSION, 0) + timedelta(minutes=m), "open": p}
            for m, p in [(120, 100), (121, 101), (125, 102), (360, 105)]
        ]
    )
    result = theoretical_results(frame, SESSION, [signal], 0.45, state_valid=True)
    assert result["9bp"]["v1941_return"] == pytest.approx((1.05 - 1 - 0.0009) * 0.45)
    assert result["18bp"]["v1941_return"] < result["9bp"]["v1941_return"]
    assert (
        result["delay_5min_9bp"]["v1941_return"] < result["receipt_next_minute_9bp"]["v1941_return"]
    )
    missing = theoretical_results(frame.iloc[:-1], SESSION, [signal], 0.45, state_valid=True)
    assert all(s["v1941_return"] is None for s in missing.values())
    assert all(s["status"] == "INCOMPLETE_PRICE" for s in missing.values())
    cash = theoretical_results(frame.iloc[:-1], SESSION, [signal], 0, state_valid=False)
    assert cash["9bp"]["v1941_return"] == 0
    assert cash["9bp"]["v1254_raw_return"] is None


def test_runner_has_no_broker_client_or_order_calls():
    root = Path(__file__).parents[2]
    tree = ast.parse((root / "scripts/run_v1941_research_shadow.py").read_text())
    forbidden = {
        "TradingClient",
        "AlpacaPaperBroker",
        "submit_order",
        "cancel_order",
        "submit",
        "cancel",
        "PaperPoolController",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id not in forbidden
        if isinstance(node, ast.Attribute):
            assert node.attr not in forbidden
    assert LABELS["global_bonferroni_passed"] is False
    assert LABELS["native_overlay_null_status"] == "NOT_COMPLETE"


def test_missed_session_never_reconstructs_signals(tmp_path, monkeypatch):
    runner = importlib.import_module("run_v1941_research_shadow")
    calls = []

    class History:
        def fetch(self, **kwargs):
            calls.append(kwargs)
            return bars()

    monkeypatch.setattr(runner.AlpacaIexHistory, "from_environment", lambda: History())
    monkeypatch.setattr(runner, "v1254_signals_at", lambda *a, **kw: pytest.fail("late signal"))
    monkeypatch.setattr(
        "sys.argv", ["runner", "--session", "2024-08-07", "--output", str(tmp_path)]
    )
    runner.main()
    ledger = ShadowLedger(tmp_path / "2024-08-07/events.sqlite3")
    assert ledger.get("state")["status"] == "MISSED_OR_INCOMPLETE"
    assert ledger.get("result")["validation_status"] == "INCOMPLETE"
    assert ledger.get("result")["missed_decisions"] == [23, 26, 29]
    assert len(calls) == 2  # context and final only, never retroactive signal snapshots


def test_live_session_captures_before_benchmark_fills_without_orders(tmp_path, monkeypatch):
    runner = importlib.import_module("run_v1941_research_shadow")
    from us_intraday_lab.paper.v449 import SleeveSignal

    chunks = []
    for offset in (0, 90, 180, 270, 360):
        frame = bars()
        frame.timestamp += timedelta(minutes=offset)
        chunks.append(frame)
    current = pd.concat(chunks)
    current = current.loc[current.timestamp < bar_time(SESSION, 78)]
    prior = current.copy()
    prior.timestamp -= timedelta(days=1)
    source = pd.concat([prior, current])

    class Clock(datetime):
        instant = bar_time(SESSION, 0) - timedelta(minutes=1)

        @classmethod
        def now(cls, tz=None):
            return cls.instant

    class History:
        def fetch(self, **kwargs):
            return source.loc[
                (source.timestamp >= kwargs["start"]) & (source.timestamp <= kwargs["end"])
            ].copy()

    def signal(frame, *, session_date, decision_bar):
        assert frame.timestamp.max() < bar_time(session_date, decision_bar + 1)
        assert Clock.instant > bar_time(session_date, decision_bar + 1)
        if decision_bar != 23:
            return ()
        return (
            SleeveSignal("anchor", "SOXL", 23, 72, 0.84, 1.0),
            SleeveSignal("component", "TQQQ", 23, 65, 0.16, 1.0),
        )

    monkeypatch.setattr(runner, "datetime", Clock)
    monkeypatch.setattr(runner, "wait_until", lambda target: setattr(Clock, "instant", target))
    monkeypatch.setattr(runner.AlpacaIexHistory, "from_environment", lambda: History())
    monkeypatch.setattr(runner, "v1254_signals_at", signal)
    monkeypatch.setattr(
        "sys.argv", ["runner", "--session", str(SESSION), "--output", str(tmp_path)]
    )
    runner.main()
    ledger = ShadowLedger(tmp_path / str(SESSION) / "events.sqlite3")
    assert ledger.get("position-29")["candidate_gross"] == 0.45
    assert ledger.get("position-29")["actual_orders"] == 0
    result = ledger.get("result")
    assert result["validation_status"] == "SIGNAL_CAPTURE_COMPLETE_NOT_STRATEGY_ADMISSION"
    for scenario in result["scenarios"].values():
        assert scenario["status"] == "COMPLETE"
        assert scenario["v1941_return"] < 0  # flat prices lose the explicitly charged cost
