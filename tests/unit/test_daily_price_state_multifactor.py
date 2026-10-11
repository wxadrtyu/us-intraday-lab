from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.diagnose_daily_price_state_multifactor import render_markdown
from us_intraday_lab.daily_price_state_multifactor import (
    FAMILIES,
    build_price_state_features,
    evaluate_grid,
    score_family,
    specifications,
    training_decision,
)


def _bars(count: int = 25) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for symbol, scale in (("AAA", 1.0), ("BBB", 2.0)):
        for ordinal, session in enumerate(pd.bdate_range("2020-11-02", periods=count)):
            close = scale * (100.0 + ordinal)
            rows.append(
                {
                    "symbol": symbol,
                    "session_date": session,
                    "open": close - 0.5,
                    "high": close + 1.0,
                    "low": close - 1.0,
                    "close": close,
                    "volume": 1_000.0 + ordinal,
                }
            )
    return pd.DataFrame(rows)


def test_specifications_freeze_exact_400_cell_grid() -> None:
    specs = specifications()

    assert len(FAMILIES) == 5
    assert len(specs) == 400
    assert len(set(specs)) == 400


def test_price_state_primitives_follow_frozen_definitions() -> None:
    features = build_price_state_features(_bars())
    aaa = features.loc[features["symbol"].eq("AAA")].reset_index(drop=True)
    last = aaa.iloc[-1]

    assert last["return_1"] == pytest.approx(124 / 123 - 1)
    assert last["return_5"] == pytest.approx(124 / 119 - 1)
    assert last["momentum_20"] == pytest.approx(124 / 104 - 1)
    assert last["close_location"] == pytest.approx(0.5)
    assert last["body_location"] == pytest.approx(0.25)
    assert last["range_ratio_20"] == pytest.approx(1.0)
    assert last["compression_5_20"] == pytest.approx(1.0)


def test_family_score_fails_closed_outside_frozen_eligibility() -> None:
    frame = pd.DataFrame(
        {
            "session_date": pd.to_datetime(["2021-01-04"] * 5),
            "return_1": [-0.10, -0.08, -0.02, 0.01, 0.03],
            "return_5": [-0.20, -0.15, -0.01, 0.02, 0.05],
            "momentum_20": [0.1] * 5,
            "close_location": [0.8, 0.4, 0.8, 0.8, 0.8],
            "body_location": [0.2] * 5,
            "range_ratio_20": [1.5] * 5,
            "compression_5_20": [0.6] * 5,
            "volume_ratio_20": [2.0] * 5,
            "failed_breakdown": [False] * 5,
        }
    )

    score = score_family(frame, "capitulation_recovery")

    assert np.isfinite(score.iloc[0])
    assert score.iloc[1:].isna().all()


def test_grid_is_complete_and_training_decision_requires_two_families() -> None:
    sessions = pd.to_datetime(["2021-01-04", "2021-01-05"])
    symbols = [f"S{index:02d}" for index in range(40)]
    score_rows = []
    cube_rows = []
    for session in sessions:
        for index, symbol in enumerate(symbols):
            score_rows.append(
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
    cells = evaluate_grid(pd.DataFrame(score_rows), pd.DataFrame(cube_rows))

    assert len(cells) == 400
    assert cells["valid"].all()
    assert training_decision(cells) == "ABANDON_DAILY_PRICE_STATE_NO_VERSION_CREATED"

    passed = pd.DataFrame(
        {
            "family": [FAMILIES[0], FAMILIES[1]],
            "valid": [True, True],
            "retention_floor_passed": [True, True],
        }
    )
    assert training_decision(passed) == "ACQUIRE_DEVELOPMENT_DAILY_PRICE_STATE_DATA"


def test_cli_markdown_discloses_zero_side_effect_contract() -> None:
    markdown = render_markdown(
        {
            "status": "COMPLETE",
            "decision": "ABANDON_DAILY_PRICE_STATE_NO_VERSION_CREATED",
            "family_eligibility": {family: {"pairs": 1, "symbols": 1, "sessions": 1} for family in FAMILIES},
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

    assert "Development or consumed data loaded: **false**" in markdown
    assert "Strategy versions created: **0**" in markdown
    assert "Order route: **FORBIDDEN**" in markdown
