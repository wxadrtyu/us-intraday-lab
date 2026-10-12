from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts.diagnose_daily_signal_intraday_multifactor import render_markdown
from us_intraday_lab.daily_signal_intraday_multifactor import (
    FAMILIES,
    evaluate_grid,
    intraday_returns,
    specifications,
    training_decision,
)


def _frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    dates = pd.to_datetime(["2021-01-04", "2021-01-05", "2021-01-06"])
    scores = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "AAA", "BBB", "AAA", "BBB"],
            "session_date": [dates[0], dates[0], dates[1], dates[1], dates[2], dates[2]],
            "score": [1.0, 0.0, 1.0, 0.0, 1.0, 0.0],
        }
    )
    trades = pd.DataFrame(
        {
            "symbol": ["AAA", "BBB", "AAA", "BBB", "AAA", "BBB"],
            "session_date": [dates[0], dates[0], dates[1], dates[1], dates[2], dates[2]],
            "open": [100.0, 100.0, 99.0, 102.0, 100.0, 103.0],
            "close": [100.0, 100.0, 108.9, 102.0, 110.0, 103.0],
            "prior_close": [100.0, 100.0, 100.0, 100.0, 108.9, 102.0],
        }
    )
    return scores, trades


def test_specifications_freeze_exact_400_cell_grid() -> None:
    specs = specifications()
    assert len(FAMILIES) == 5
    assert len(specs) == 400
    assert len(set(specs)) == 400


@pytest.mark.parametrize(
    ("gap_mode", "expected_return"),
    [
        ("all", 0.10 - 0.0009),
        ("pullback", 0.10 - 0.0009),
        ("quiet", 0.10 - 0.0009),
        ("followthrough", -0.0009),
    ],
)
def test_intraday_returns_apply_known_open_gap_modes(
    gap_mode: str, expected_return: float
) -> None:
    scores, trades = _frames()
    returns, sessions, valid = intraday_returns(
        scores,
        trades,
        top_count=1,
        signal_lag=1,
        gap_mode=gap_mode,
        cost_rate=0.0009,
        evaluation_start=pd.Timestamp("2021-01-05").date(),
        evaluation_end=pd.Timestamp("2021-01-05").date(),
    )
    assert valid
    assert sessions == 1
    assert returns.iloc[0] == pytest.approx(expected_return)


def test_intraday_returns_fail_closed_for_selected_missing_close() -> None:
    scores, trades = _frames()
    trades.loc[(trades["symbol"] == "AAA") & (trades["session_date"] == "2021-01-05"), "close"] = float("nan")
    _, _, valid = intraday_returns(
        scores,
        trades,
        top_count=1,
        signal_lag=1,
        gap_mode="all",
        cost_rate=0.0009,
    )
    assert valid is False


def test_cached_grid_matches_frozen_400_cell_contract() -> None:
    scores, trades = _frames()
    feature_scores = scores.rename(
        columns={"session_date": "feature_date"}
    ).drop(columns="score")
    for index, family in enumerate(FAMILIES):
        feature_scores[family] = [float(index + 1), float(index)] * 3

    cells = evaluate_grid(
        feature_scores,
        trades,
        evaluation_start=pd.Timestamp("2021-01-05").date(),
        evaluation_end=pd.Timestamp("2021-01-06").date(),
    )

    assert len(cells) == 400
    assert cells["valid"].all()


def test_training_decision_requires_zero_invalid_and_two_retained_families() -> None:
    cells = pd.DataFrame(
        {
            "family": [FAMILIES[0], FAMILIES[1]],
            "valid": [True, True],
            "retention_floor_passed": [True, True],
        }
    )
    assert training_decision(cells) == "ACQUIRE_DEVELOPMENT_DAILY_SIGNAL_INTRADAY_DATA"
    cells.loc[1, "valid"] = False
    assert training_decision(cells) == "ABANDON_DAILY_SIGNAL_INTRADAY_NO_VERSION_CREATED"


def test_cli_starts_directly_and_discloses_safety_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [sys.executable, "scripts/diagnose_daily_signal_intraday_multifactor.py", "--help"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    markdown = render_markdown(
        {
            "status": "COMPLETE",
            "decision": "ABANDON_DAILY_SIGNAL_INTRADAY_NO_VERSION_CREATED",
            "symbols": 527,
            "cells_completed": 400,
            "invalid_cells": 0,
            "retained_cells": 0,
            "retained_families": [],
            "daily_source_sha256": "daily",
            "symbol_container_sha256": "container",
            "cells_sha256": "cells",
            "strategy_versions_created": 0,
            "paper_activation": False,
            "order_route": "FORBIDDEN",
        }
    )
    assert "News or issuer-event data loaded: **false**" in markdown
    assert "Development or consumed data loaded: **false**" in markdown
