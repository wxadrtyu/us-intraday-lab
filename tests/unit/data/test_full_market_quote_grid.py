from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from us_intraday_lab.data.full_market_quote_grid import (
    build_expected_quote_grid,
    resolve_quote_targets,
)


def test_expected_grid_crosses_every_eligible_symbol_session_clock_and_target() -> None:
    decisions = pd.DataFrame(
        {
            "month": [date(2026, 3, 1), date(2026, 3, 1)],
            "symbol": ["AAA", "BBB"],
            "eligible": [True, False],
        }
    )

    result = build_expected_quote_grid(
        decisions=decisions,
        start=date(2026, 3, 2),
        end=date(2026, 3, 2),
        decision_bars=(2,),
        holding_bars=(1, 2),
    )

    assert result["symbol"].unique().tolist() == ["AAA"]
    assert result["target_role"].tolist() == [
        "decision_prior",
        "entry",
        "delay_entry_5m",
        "exit_1bar",
        "exit_2bar",
    ]
    assert result["match_direction"].tolist() == [
        "strictly_prior",
        "at_or_after",
        "at_or_after",
        "at_or_after",
        "at_or_after",
    ]
    assert result["target_timestamp"].tolist() == [
        datetime(2026, 3, 2, 14, 45, tzinfo=UTC),
        datetime(2026, 3, 2, 14, 45, tzinfo=UTC),
        datetime(2026, 3, 2, 14, 50, tzinfo=UTC),
        datetime(2026, 3, 2, 14, 50, tzinfo=UTC),
        datetime(2026, 3, 2, 14, 55, tzinfo=UTC),
    ]


def test_quote_resolution_is_causal_bounded_and_preserves_missing_targets() -> None:
    cutoff = datetime(2026, 3, 2, 14, 45, tzinfo=UTC)
    targets = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "BBB"],
            "target_timestamp": [cutoff, cutoff, cutoff],
            "target_role": ["decision_prior", "entry", "entry"],
            "match_direction": ["strictly_prior", "at_or_after", "at_or_after"],
        }
    )
    quotes = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "AAA"],
            "timestamp": [
                cutoff - timedelta(seconds=121),
                cutoff - timedelta(seconds=1),
                cutoff + timedelta(milliseconds=500),
            ],
            "bid_price": [98.0, 99.0, 100.0],
            "ask_price": [99.0, 101.0, 102.0],
            "bid_size": [1.0, 30.0, 20.0],
            "ask_size": [1.0, 10.0, 20.0],
        }
    )

    result = resolve_quote_targets(targets=targets, quotes=quotes, tolerance_seconds=120)

    prior = result.loc[result["target_role"].eq("decision_prior")].iloc[0]
    entry = result.loc[
        result["symbol"].eq("AAA") & result["target_role"].eq("entry")
    ].iloc[0]
    missing = result.loc[result["symbol"].eq("BBB")].iloc[0]
    assert prior["quote_timestamp"] == cutoff - timedelta(seconds=1)
    assert prior["quote_age_ms"] == 1000.0
    assert entry["quote_timestamp"] == cutoff + timedelta(milliseconds=500)
    assert entry["quote_age_ms"] == 500.0
    assert not bool(missing["quote_available"])
    assert pd.isna(missing["midpoint"])
