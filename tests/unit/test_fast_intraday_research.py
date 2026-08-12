from __future__ import annotations

import numpy as np

from us_intraday_lab.fast_intraday_research import metrics


def test_metrics_reports_compounded_return_drawdown_ir_and_trade_quality() -> None:
    returns = np.array([0.02, -0.01, 0.03, 0.0, -0.005], dtype=float)
    benchmark = np.array([0.01, -0.005, 0.01, 0.0, -0.002], dtype=float)
    result = metrics(returns, benchmark, np.array([True, True, True, False, True]))
    assert result["total_return"] == pytest.approx(np.prod(1.0 + returns) - 1.0)
    assert result["max_drawdown"] > 0.0
    assert result["profit_factor"] > 1.0
    assert result["trades"] == 4
    assert np.isfinite(result["information_ratio"])


def test_metrics_treats_zero_exposure_as_zero_benchmark() -> None:
    returns = np.array([0.0, 0.01, 0.0, -0.005], dtype=float)
    benchmark = np.array([0.3, 0.002, -0.2, -0.001], dtype=float)
    active = np.array([False, True, False, True])
    result = metrics(returns, benchmark, active)
    expected = np.array([0.0, 0.002, 0.0, -0.001])
    deviation = np.std(returns - expected, ddof=1)
    assert result["information_ratio"] == pytest.approx(
        np.mean(returns - expected) / deviation * np.sqrt(252.0)
    )


import pytest
