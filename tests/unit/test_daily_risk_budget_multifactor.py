from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from scripts.diagnose_daily_risk_budget_multifactor import render_markdown
from us_intraday_lab.daily_risk_budget_multifactor import (
    FAMILIES,
    capped_inverse_volatility_weights,
    portfolio_returns,
    specifications,
    training_decision,
)


def test_specifications_freeze_exact_400_cell_grid() -> None:
    specs = specifications()

    assert len(FAMILIES) == 5
    assert len(specs) == 400
    assert len(set(specs)) == 400


def test_inverse_volatility_weights_cap_names_and_leave_residual_cash() -> None:
    weights = capped_inverse_volatility_weights(
        pd.Series({"AAA": 0.10, "BBB": 0.20, "CCC": 0.40}), cap=0.10
    )

    assert weights == pytest.approx({"AAA": 0.10, "BBB": 0.10, "CCC": 0.10})
    assert sum(weights.values()) == pytest.approx(0.30)


def test_portfolio_applies_risk_exposure_lag_and_turnover_cost() -> None:
    dates = pd.to_datetime(["2021-01-04", "2021-01-05", "2021-01-06"])
    scores = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "AAA"],
            "session_date": dates,
            "score": [1.0, 1.0, 1.0],
            "realized_volatility_20": [0.20, 0.20, 0.20],
            "eligible": [True, True, True],
        }
    )
    opens = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "AAA"],
            "session_date": dates,
            "open": [100.0, 110.0, 121.0],
        }
    )
    exposure = pd.Series([0.50, 0.50, 0.50], index=dates)

    returns, sessions, valid = portfolio_returns(
        scores,
        opens,
        exposure,
        top_count=1,
        holding_sessions=1,
        signal_lag=1,
        cost_rate=0.0009,
    )

    assert valid
    assert sessions == 1
    assert returns.iloc[0] == 0.0
    # The 10% name cap is multiplied by 50% market exposure. Turnover from cash
    # is 5%, so the entry cost is 0.0009 * 0.05.
    assert returns.iloc[1] == pytest.approx(0.05 * 0.10 - 0.0009 * 0.05)


def test_portfolio_fails_closed_when_selected_next_open_is_missing() -> None:
    dates = pd.to_datetime(["2021-01-04", "2021-01-05", "2021-01-06"])
    scores = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "AAA"],
            "session_date": dates,
            "score": [1.0, 1.0, 1.0],
            "realized_volatility_20": [0.20, 0.20, 0.20],
            "eligible": [True, True, True],
        }
    )
    opens = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "BBB", "BBB", "BBB"],
            "session_date": [dates[0], dates[1], *dates],
            "open": [100.0, 110.0, 50.0, 50.0, 50.0],
        }
    )

    _, _, valid = portfolio_returns(
        scores,
        opens,
        pd.Series(1.0, index=dates),
        top_count=1,
        holding_sessions=1,
        signal_lag=1,
        cost_rate=0.0009,
    )

    assert valid is False


def test_training_decision_requires_zero_invalid_and_two_retained_families() -> None:
    cells = pd.DataFrame(
        {
            "family": [FAMILIES[0], FAMILIES[1]],
            "valid": [True, True],
            "retention_floor_passed": [True, True],
        }
    )

    assert training_decision(cells) == "ACQUIRE_DEVELOPMENT_DAILY_RISK_BUDGET_DATA"
    cells.loc[1, "retention_floor_passed"] = False
    assert training_decision(cells) == "ABANDON_DAILY_RISK_BUDGET_NO_VERSION_CREATED"
    cells.loc[1, "retention_floor_passed"] = True
    cells.loc[1, "valid"] = False
    assert training_decision(cells) == "ABANDON_DAILY_RISK_BUDGET_NO_VERSION_CREATED"


def test_cli_starts_directly_and_discloses_safety_contract() -> None:
    root = Path(__file__).resolve().parents[2]
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/diagnose_daily_risk_budget_multifactor.py",
            "--help",
        ],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    markdown = render_markdown(
        {
            "status": "COMPLETE",
            "decision": "ABANDON_DAILY_RISK_BUDGET_NO_VERSION_CREATED",
            "symbols": 527,
            "cells_completed": 400,
            "invalid_cells": 0,
            "retained_cells": 0,
            "retained_families": [],
            "daily_source_sha256": "daily",
            "symbol_container_sha256": "container",
            "cells_sha256": "cells",
            "strategy_versions_created": 0,
            "development_or_consumed_loaded": False,
            "paper_activation": False,
            "order_route": "FORBIDDEN",
        }
    )
    assert "Development or consumed data loaded: **false**" in markdown
    assert "Order route: **FORBIDDEN**" in markdown
    assert "News or issuer-event data loaded: **false**" in markdown
