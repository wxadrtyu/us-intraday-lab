from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from us_intraday_lab.tp_ensemble import (
    TpEnsembleParameters,
    evaluate_tp_ensemble,
    exclude_tp_symbol,
    slice_tp_evaluation,
    tp_metrics,
    tp_null_distributions,
    validate_period_sessions,
)


def _fixture(tmp_path: Path) -> tuple[pd.DataFrame, pd.Series, Path, tuple[str, ...]]:
    universe = tuple(f"S{index:02d}" for index in range(51))
    sessions = tuple(date(2025, 1, 2) + timedelta(days=index) for index in range(30))
    rows = []
    raw_rows = []
    timezone = ZoneInfo("America/New_York")
    for session_index, session in enumerate(sessions):
        for symbol_index, symbol in enumerate(universe):
            is_top = symbol_index == 0
            rows.append(
                {
                    "session_date": session,
                    "symbol": symbol,
                    "day_open": 100.0,
                    "close_45": 101.0 if is_top else 100.0,
                    "open_46": 100.0,
                    "open_300": 101.0,
                    "open_330": 101.0,
                    "cum_volume_45": 200.0 if is_top and session_index >= 20 else 100.0,
                    "vwap_45": 100.5 if is_top else 100.0,
                    "range_high_45": 102.0,
                    "range_low_45": 99.0,
                    "spy_current_45": 0.003,
                    "spy_current_300": 0.006,
                    "spy_current_330": 0.007,
                }
            )
        start = datetime.combine(session, time(10, 16), timezone)
        for minute in range(284):
            raw_rows.append(
                {
                    "datetime": start + timedelta(minutes=minute),
                    "symbol": universe[0],
                    "high": 103.0 if minute >= 20 else 101.0,
                    "spy_logret_1": 0.00001,
                }
            )
    raw_path = tmp_path / "bars.parquet"
    pd.DataFrame(raw_rows).to_parquet(raw_path, index=False)
    benchmark = pd.Series(0.001, index=pd.Index(sessions, name="session_date"))
    return pd.DataFrame(rows), benchmark, raw_path, universe


def test_exact_evaluator_composes_stock_and_fallback_without_exceeding_gross(
    tmp_path: Path,
) -> None:
    frame, benchmark, raw_path, universe = _fixture(tmp_path)
    evaluation = evaluate_tp_ensemble(
        frame,
        benchmark,
        (raw_path,),
        TpEnsembleParameters(0.005, 0.6, 300),
        universe=universe,
        round_trip_cost=0.0009,
    )

    assert evaluation.trade_count == 29
    assert set(evaluation.action) == {"NONE", "SPY", "STOCK"}
    assert evaluation.components.abs().sum(axis=1).max() < 1.0
    assert max(evaluation.session_returns) == pytest.approx(0.0191)
    assert tp_metrics(evaluation, fold_count=5)["trades"] == 29

    sliced = slice_tp_evaluation(evaluation, evaluation.sessions[-10:])
    excluded = exclude_tp_symbol(evaluation, universe[0])
    assert sliced.trade_count == 10
    assert "STOCK" not in set(excluded.action)


def test_null_evidence_is_deterministic(tmp_path: Path) -> None:
    frame, benchmark, raw_path, universe = _fixture(tmp_path)
    evaluation = evaluate_tp_ensemble(
        frame,
        benchmark,
        (raw_path,),
        TpEnsembleParameters(0.005, 0.65, 330),
        universe=universe,
        round_trip_cost=0.0009,
    )

    first = tp_null_distributions(evaluation, repetitions=100, seed=19)
    second = tp_null_distributions(evaluation, repetitions=100, seed=19)

    assert first == second
    assert all(len(values) == 100 for values in first.values())


def test_period_scope_normalizes_date_and_timestamp_values() -> None:
    sessions: tuple[object, ...] = (
        date(2026, 1, 2),
        pd.Timestamp("2026-01-05"),
    )

    observed = validate_period_sessions(
        sessions,
        start="2026-01-01",
        end_exclusive="2026-07-01",
        minimum_sessions=2,
    )

    assert observed == (pd.Timestamp("2026-01-02"), pd.Timestamp("2026-01-05"))
    with pytest.raises(ValueError, match="outside the frozen scope"):
        validate_period_sessions(
            (pd.Timestamp("2026-07-01"),),
            start="2026-01-01",
            end_exclusive="2026-07-01",
            minimum_sessions=1,
        )
