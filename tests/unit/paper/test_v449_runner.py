from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from scripts.run_v449_alpaca_paper import MAX_ENTRY_LATENESS, _entry_window_open, _target_complete
from tests.fakes.broker import FakePaperBroker
from us_intraday_lab.paper.v449 import V449PaperLedger

SESSION = date(2026, 8, 24)
OPEN = datetime(2026, 8, 24, 13, 30, tzinfo=UTC)


def _bars(*, missing: dict[str, set[int]] | None = None) -> pd.DataFrame:
    omitted = missing or {}
    rows: list[dict[str, object]] = []
    for symbol in ("TQQQ", "SOXL", "XLC"):
        for minute in range(120):
            if minute in omitted.get(symbol, set()):
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "timestamp": OPEN + timedelta(minutes=minute),
                    "open": 100.0,
                    "high": 100.0,
                    "low": 100.0,
                    "close": 100.0,
                    "volume": 1.0,
                }
            )
    return pd.DataFrame(rows)


def test_target_complete_allows_sparse_minutes_and_ignores_context_etfs() -> None:
    bars = _bars(
        missing={
            "TQQQ": {1, 2, 3, 4, 16, 17, 18},
            "XLC": set(range(90)),
        }
    )

    assert _target_complete(bars, SESSION, through_bar=23) is True


def test_target_complete_rejects_a_wholly_missing_traded_asset_bucket() -> None:
    bars = _bars(missing={"TQQQ": set(range(80, 85))})

    assert _target_complete(bars, SESSION, through_bar=23) is False


def test_target_complete_does_not_accept_a_future_bucket_for_a_missing_bucket() -> None:
    bars = _bars(missing={"SOXL": set(range(55, 60))})

    assert _target_complete(bars, SESSION, through_bar=23) is False


def test_entry_window_is_rechecked_after_slow_market_data_fetch() -> None:
    eligible = OPEN + timedelta(hours=2)
    assert _entry_window_open(eligible + MAX_ENTRY_LATENESS, eligible)
    assert not _entry_window_open(eligible + MAX_ENTRY_LATENESS + timedelta(microseconds=1), eligible)


def test_retired_consolidated_runner_evaluates_no_member(monkeypatch) -> None:
    from scripts import run_v449_alpaca_paper as runner

    def inactive(*args, **kwargs):
        raise AssertionError("retired strategy must not evaluate")

    monkeypatch.setattr(runner, "v247_signals_at", inactive)
    monkeypatch.setattr(runner, "signals_at", inactive)
    monkeypatch.setattr(runner, "v798_signals_at", inactive)
    monkeypatch.setattr(runner, "v1254_signals_at", inactive)
    assert runner._pool_signals(None, session_date=SESSION, decision_bar=23) == {}


def test_retired_consolidated_runner_builds_no_controller(tmp_path) -> None:
    from scripts.run_v449_alpaca_paper import _pool_controllers

    broker = FakePaperBroker(now=OPEN)
    controllers = _pool_controllers(broker, V449PaperLedger(tmp_path / "pool.sqlite3"))
    assert controllers == {}


def test_consolidation_does_not_change_decision_clocks() -> None:
    from scripts.run_v449_alpaca_paper import COMPONENT_EXIT, ENTRY_DECISIONS, EXIT_BAR

    assert ENTRY_DECISIONS == (23, 26, 29)
    assert COMPONENT_EXIT == 65
    assert EXIT_BAR == 72
