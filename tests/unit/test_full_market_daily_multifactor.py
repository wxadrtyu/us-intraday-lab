from __future__ import annotations

import pandas as pd
import pytest

from us_intraday_lab.full_market_daily_multifactor import (
    FAMILIES,
    HOLDING_SESSIONS,
    REBALANCE_SESSIONS,
    TOP_COUNTS,
    attach_point_in_time_eligibility,
    specifications,
    validate_monthly_universe,
)


def _universe() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "BBB", "BBB"],
            "month": pd.to_datetime(
                ["2021-01-01", "2021-02-01", "2021-01-01", "2021-02-01"]
            ),
            "eligible": [True, False, False, True],
            "information_cutoff": pd.to_datetime(
                ["2020-12-31", "2021-01-29", "2020-12-31", "2021-01-29"]
            ),
        }
    )


def test_specifications_freeze_exact_full_market_400_cell_grid() -> None:
    specs = specifications()

    assert len(specs) == 400
    assert len(set(specs)) == 400
    assert len(FAMILIES) == 5
    assert REBALANCE_SESSIONS == (5, 10, 20, 21)
    assert HOLDING_SESSIONS == (5, 10, 20, 42)
    assert TOP_COUNTS == (10, 20, 40, 80, 120)


def test_validate_monthly_universe_rejects_duplicate_symbol_month() -> None:
    universe = pd.concat([_universe(), _universe().iloc[[0]]], ignore_index=True)

    with pytest.raises(ValueError, match="UNIVERSE_KEY_DUPLICATE"):
        validate_monthly_universe(universe)


def test_validate_monthly_universe_rejects_noncausal_cutoff() -> None:
    universe = _universe()
    universe.loc[0, "information_cutoff"] = pd.Timestamp("2021-01-01")

    with pytest.raises(ValueError, match="UNIVERSE_CUTOFF_NOT_PRIOR"):
        validate_monthly_universe(universe)


def test_attach_point_in_time_eligibility_uses_same_calendar_month() -> None:
    bars = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "BBB", "BBB"],
            "session_date": pd.to_datetime(
                ["2021-01-15", "2021-02-12", "2021-01-15", "2021-02-12"]
            ),
            "open": [10.0, 11.0, 20.0, 21.0],
            "high": [10.5, 11.5, 20.5, 21.5],
            "low": [9.5, 10.5, 19.5, 20.5],
            "close": [10.2, 11.2, 20.2, 21.2],
            "volume": [1000, 1100, 2000, 2100],
            "vwap": [10.1, 11.1, 20.1, 21.1],
            "trade_count": [100, 110, 200, 210],
        }
    )

    attached = attach_point_in_time_eligibility(bars, _universe())

    assert list(attached[["symbol", "session_date"]].itertuples(index=False, name=None)) == [
        ("AAA", pd.Timestamp("2021-01-15")),
        ("BBB", pd.Timestamp("2021-02-12")),
    ]
    assert attached["universe_month"].tolist() == list(
        pd.to_datetime(["2021-01-01", "2021-02-01"])
    )


def test_attach_point_in_time_eligibility_rejects_duplicate_daily_key() -> None:
    bars = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA"],
            "session_date": pd.to_datetime(["2021-01-15", "2021-01-15"]),
            "open": [10.0, 10.0],
            "high": [10.5, 10.5],
            "low": [9.5, 9.5],
            "close": [10.2, 10.2],
            "volume": [1000, 1000],
            "vwap": [10.1, 10.1],
            "trade_count": [100, 100],
        }
    )

    with pytest.raises(ValueError, match="DAILY_KEY_DUPLICATE"):
        attach_point_in_time_eligibility(bars, _universe())


def test_attach_point_in_time_eligibility_rejects_forbidden_columns() -> None:
    bars = pd.DataFrame(
        {
            "symbol": ["AAA"],
            "session_date": pd.to_datetime(["2021-01-15"]),
            "open": [10.0],
            "high": [10.5],
            "low": [9.5],
            "close": [10.2],
            "volume": [1000],
            "vwap": [10.1],
            "trade_count": [100],
            "headline": ["forbidden"],
        }
    )

    with pytest.raises(ValueError, match="FORBIDDEN_INPUT_COLUMN"):
        attach_point_in_time_eligibility(bars, _universe())
