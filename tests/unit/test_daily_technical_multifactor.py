from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.diagnose_daily_technical_multifactor import render_markdown
from us_intraday_lab.daily_technical_multifactor import (
    FAMILIES,
    build_daily_features,
    daily_returns,
    evaluate_grid,
    map_features_to_sessions,
    specifications,
    training_decision,
)


def _business_dates(count: int, start: str = "2020-09-01") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=count)


def _daily_bars(count: int = 65) -> pd.DataFrame:
    dates = _business_dates(count)
    rows: list[dict[str, object]] = []
    for symbol, step in (("AAA", 0.01), ("BBB", 0.0)):
        for ordinal, session in enumerate(dates):
            close = float(np.exp(step * ordinal))
            rows.append(
                {
                    "symbol": symbol,
                    "session_date": session,
                    "open": close,
                    "high": close * 1.01,
                    "low": close * 0.99,
                    "close": close,
                    "volume": float(1_000 + ordinal),
                }
            )
    return pd.DataFrame(rows)


def test_specifications_freeze_exact_400_cell_grid() -> None:
    specs = specifications()

    assert len(specs) == 400
    assert len(set(specs)) == 400
    assert len(FAMILIES) == 5


def test_daily_features_use_exact_rolling_definitions() -> None:
    bars = _daily_bars()

    features = build_daily_features(bars)
    aaa = features.loc[features["symbol"].eq("AAA")].reset_index(drop=True)
    last = aaa.iloc[-1]

    assert np.isnan(aaa.iloc[58]["momentum_60_5"])
    assert last["momentum_20_5"] == pytest.approx(0.15)
    assert last["momentum_60_5"] == pytest.approx(0.55)
    assert last["reversal_5"] == pytest.approx(-0.05)
    assert last["trend_efficiency_20"] == pytest.approx(1.0)
    assert last["drawdown_60"] == pytest.approx(0.0)
    assert np.isfinite(last["residual_momentum_60_5"])


def test_feature_mapping_uses_strictly_previous_daily_bar() -> None:
    features = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA"],
            "feature_date": pd.to_datetime(["2021-01-04", "2021-01-05"]),
            "balanced_trend": [1.0, 9.0],
        }
    )
    sessions = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA"],
            "session_date": pd.to_datetime(["2021-01-05", "2021-01-06"]),
        }
    )

    mapped = map_features_to_sessions(features, sessions)

    assert mapped["balanced_trend"].tolist() == [1.0, 9.0]
    assert mapped["feature_date"].tolist() == list(
        pd.to_datetime(["2021-01-04", "2021-01-05"])
    )


def test_daily_returns_apply_cost_and_delay_prices() -> None:
    selected = pd.DataFrame(
        {
            "session_date": pd.to_datetime(["2021-01-04", "2021-01-04"]),
            "p1_open": [100.0, 200.0],
            "p2_open": [101.0, 202.0],
            "p3_open": [103.0, 206.0],
        }
    )
    calendar = pd.DatetimeIndex(pd.to_datetime(["2021-01-04", "2021-01-05"]))

    standard, sessions, valid = daily_returns(
        selected,
        entry="p1_open",
        exit_column="p2_open",
        cost=0.0009,
        calendar=calendar,
    )
    delayed, _, delayed_valid = daily_returns(
        selected,
        entry="p2_open",
        exit_column="p3_open",
        cost=0.0009,
        calendar=calendar,
    )

    assert valid and delayed_valid
    assert sessions == 1
    assert standard.iloc[0] == pytest.approx(0.0091)
    assert delayed.iloc[0] == pytest.approx((103 / 101 - 1 + 206 / 202 - 1) / 2 - 0.0009)
    assert standard.iloc[1] == 0.0


def test_daily_returns_reject_nonpositive_prices() -> None:
    selected = pd.DataFrame(
        {
            "session_date": pd.to_datetime(["2021-01-04"]),
            "p1_open": [0.0],
            "p2_open": [101.0],
        }
    )

    _, _, valid = daily_returns(
        selected,
        entry="p1_open",
        exit_column="p2_open",
        cost=0.0009,
        calendar=pd.DatetimeIndex(pd.to_datetime(["2021-01-04"])),
    )

    assert valid is False


def test_evaluate_grid_is_complete_and_deterministic() -> None:
    sessions = pd.to_datetime(["2021-01-04", "2021-01-05"])
    symbols = [f"S{index:02d}" for index in range(40)]
    feature_rows = []
    cube_rows = []
    for session in sessions:
        for index, symbol in enumerate(symbols):
            feature_rows.append(
                {
                    "symbol": symbol,
                    "session_date": session,
                    **{family: float(index) for family in FAMILIES},
                }
            )
            for bar_idx in (2, 5, 11, 17, 23):
                cube_rows.append(
                    {
                        "symbol": symbol,
                        "session_date": session,
                        "bar_idx": bar_idx,
                        "p1_open": 100.0,
                        "p2_open": 100.1,
                        "p3_open": 100.2,
                        "p5_open": 100.4,
                        "p7_open": 100.6,
                        "p8_open": 100.7,
                    }
                )

    cells = evaluate_grid(pd.DataFrame(feature_rows), pd.DataFrame(cube_rows))

    assert len(cells) == 400
    assert cells["valid"].all()
    assert set(cells["top_count"]) == {5, 10, 20, 40}
    assert cells["retention_floor_passed"].eq(False).all()


def test_training_decision_requires_zero_invalid_and_two_families() -> None:
    cells = pd.DataFrame(
        {
            "family": ["balanced_trend", "residual_trend"],
            "valid": [True, True],
            "retention_floor_passed": [True, True],
        }
    )

    assert training_decision(cells) == "ACQUIRE_DEVELOPMENT_DAILY_TECHNICAL_DATA"
    cells.loc[1, "retention_floor_passed"] = False
    assert training_decision(cells) == "ABANDON_DAILY_TECHNICAL_NO_VERSION_CREATED"
    cells.loc[1, ["valid", "retention_floor_passed"]] = [False, True]
    assert training_decision(cells) == "ABANDON_DAILY_TECHNICAL_NO_VERSION_CREATED"


def test_cli_markdown_discloses_training_only_safety_contract() -> None:
    markdown = render_markdown(
        {
            "status": "COMPLETE",
            "decision": "ABANDON_DAILY_TECHNICAL_NO_VERSION_CREATED",
            "eligible_symbol_sessions": 100,
            "eligible_symbols": 20,
            "cells_completed": 400,
            "invalid_cells": 0,
            "retained_cells": 0,
            "retained_families": [],
            "daily_source_sha256": "daily",
            "event_cube_sha256": "cube",
            "cells_sha256": "cells",
            "strategy_versions_created": 0,
            "paper_activation": False,
            "order_route": "FORBIDDEN",
        }
    )

    assert "527-symbol 2021-2023 coverage-limited sample; not full market" in markdown
    assert "Development or consumed data loaded: **false**" in markdown
    assert "Strategy versions created: **0**" in markdown
    assert "Order route: **FORBIDDEN**" in markdown
