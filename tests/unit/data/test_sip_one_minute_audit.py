from __future__ import annotations

from datetime import date

import pandas as pd

from us_intraday_lab.data.sip_one_minute_audit import audit_one_minute_paths


def test_audit_counts_exact_point_in_time_paths_without_filling() -> None:
    opening = pd.Timestamp("2023-12-29T14:30:00Z")
    bars = pd.DataFrame(
        [
            (symbol, opening + pd.Timedelta(minutes=minute))
            for symbol, minutes in {"AAA": range(12), "BBB": range(11)}.items()
            for minute in minutes
        ],
        columns=["symbol", "timestamp"],
    )
    decisions = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "CCC"],
            "month": [date(2023, 12, 1)] * 3,
            "eligible": [True, True, False],
        }
    )
    result = audit_one_minute_paths(
        bars=bars,
        decisions=decisions,
        session=date(2023, 12, 29),
        start_minute=0,
        path_minutes=12,
        source_complete=False,
    )
    assert result["eligible_symbols"] == 2
    assert result["observed_required_minutes"] == 23
    assert result["expected_required_minutes"] == 24
    assert result["complete_paths"] == 1
    assert result["complete_path_ratio"] == 0.5
    assert result["strategy_metrics_permitted"] is False
    assert "INCOMPLETE_SOURCE_GRID" in result["rejection_reasons"]


def test_audit_rejects_duplicate_and_wrong_month() -> None:
    opening = pd.Timestamp("2023-12-29T14:30:00Z")
    bars = pd.DataFrame({"symbol": ["AAA", "AAA"], "timestamp": [opening, opening]})
    decisions = pd.DataFrame({"symbol": ["AAA"], "month": [date(2023, 11, 1)], "eligible": [True]})
    result = audit_one_minute_paths(
        bars=bars,
        decisions=decisions,
        session=date(2023, 12, 29),
        start_minute=0,
        path_minutes=12,
        source_complete=True,
    )
    assert "DUPLICATE_SYMBOL_MINUTE" in result["rejection_reasons"]
    assert "NO_POINT_IN_TIME_ELIGIBLE_SYMBOLS" in result["rejection_reasons"]
