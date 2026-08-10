from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from us_intraday_lab.long_horizon.hf_source import aggregate_hf_regular_minutes


def _rows(*, omit_spy_index: int | None = None) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    start = datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    for ticker in ("SPY", "IWM"):
        for index in range(10):
            if ticker == "SPY" and index == omit_spy_index:
                continue
            price = 100.0 + index
            rows.append(
                {
                    "ticker": ticker,
                    "timestamp": start + timedelta(minutes=index),
                    "open": price,
                    "high": price + 1.0,
                    "low": price - 1.0,
                    "close": price + 0.5,
                    "volume": 10.0 + index,
                }
            )
        rows.append(
            {
                "ticker": ticker,
                "timestamp": datetime(2024, 1, 2, 13, tzinfo=UTC),
                "open": 1.0,
                "high": 1.0,
                "low": 1.0,
                "close": 1.0,
                "volume": 1.0,
            }
        )
    return pd.DataFrame(rows)


def test_hf_rows_are_regular_hours_only_and_aggregate_causally() -> None:
    result = aggregate_hf_regular_minutes(
        _rows(), symbols=("SPY", "IWM"), expected_minutes_per_session=10
    )

    assert result.accepted_sessions == (date(2024, 1, 2),)
    assert result.rejected_sessions == ()
    assert len(result.bars) == 4
    spy = result.bars[result.bars["symbol"] == "SPY"].reset_index(drop=True)
    assert spy.loc[0, "timestamp"] == pd.Timestamp("2024-01-02T14:30:00Z")
    assert spy.loc[0, "available_at"] == pd.Timestamp("2024-01-02T14:35:00Z")
    assert spy.loc[0, ["open", "high", "low", "close", "volume"]].tolist() == [
        100.0,
        105.0,
        99.0,
        104.5,
        60.0,
    ]


def test_hf_rows_reject_a_session_unless_both_symbols_are_complete() -> None:
    result = aggregate_hf_regular_minutes(
        _rows(omit_spy_index=3),
        symbols=("SPY", "IWM"),
        expected_minutes_per_session=10,
    )

    assert result.bars.empty
    assert result.accepted_sessions == ()
    assert result.rejected_sessions == (date(2024, 1, 2),)


def test_sparse_minute_mode_accepts_only_complete_observed_five_minute_buckets() -> None:
    result = aggregate_hf_regular_minutes(
        _rows(omit_spy_index=3),
        symbols=("SPY", "IWM"),
        expected_minutes_per_session=10,
        allow_sparse_minutes_with_complete_buckets=True,
    )

    assert result.accepted_sessions == (date(2024, 1, 2),)
    spy = result.bars[result.bars["symbol"] == "SPY"].reset_index(drop=True)
    assert spy.loc[0, "timestamp"] == pd.Timestamp("2024-01-02T14:30:00Z")
    assert spy.loc[0, "available_at"] == pd.Timestamp("2024-01-02T14:35:00Z")
    assert spy.loc[0, "volume"] == 47.0

    missing_bucket = _rows().loc[
        lambda rows: (
            ~(
                (rows["ticker"] == "SPY")
                & rows["timestamp"].between(
                    pd.Timestamp("2024-01-02T14:35:00Z"),
                    pd.Timestamp("2024-01-02T14:39:00Z"),
                )
            )
        )
    ]
    rejected = aggregate_hf_regular_minutes(
        missing_bucket,
        symbols=("SPY", "IWM"),
        expected_minutes_per_session=10,
        allow_sparse_minutes_with_complete_buckets=True,
    )
    assert rejected.accepted_sessions == ()
    assert rejected.rejected_sessions == (date(2024, 1, 2),)


def test_hf_rows_reject_only_the_session_with_conflicting_duplicate_minutes() -> None:
    first = _rows()
    second = _rows().copy()
    second["timestamp"] = second["timestamp"] + pd.Timedelta(days=1)
    duplicate = second.loc[
        (second["ticker"] == "IWM") & (second["timestamp"] == pd.Timestamp("2024-01-03T14:33:00Z"))
    ].copy()
    duplicate["open"] = duplicate["open"] + 0.25
    source = pd.concat([first, second, duplicate], ignore_index=True)

    result = aggregate_hf_regular_minutes(
        source,
        symbols=("SPY", "IWM"),
        expected_minutes_per_session=10,
    )

    assert result.accepted_sessions == (date(2024, 1, 2),)
    assert result.rejected_sessions == (date(2024, 1, 3),)
    assert len(result.bars) == 4
