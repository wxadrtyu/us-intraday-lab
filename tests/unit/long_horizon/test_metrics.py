import math
import statistics

import pytest

from us_intraday_lab.long_horizon.metrics import compute_long_horizon_oos_metrics


def test_oos_metrics_use_geometric_return_and_sample_tracking_error() -> None:
    metrics = compute_long_horizon_oos_metrics(
        strategy_session_returns=(0.01, -0.005, 0.008),
        benchmark_session_returns=(0.004, -0.002, 0.003),
        cost_1_5x_session_returns=(0.009, -0.006, 0.007),
        annualization_sessions=252,
    )
    expected_total = math.prod((1.009, 0.994, 1.007)) - 1.0
    assert metrics.cost_1_5x_total_return == pytest.approx(expected_total)
    assert metrics.cost_1_5x_annualized_return == pytest.approx(
        (1.0 + expected_total) ** (252 / 3) - 1.0
    )
    active = (0.006, -0.003, 0.005)
    assert metrics.information_ratio == pytest.approx(
        statistics.fmean(active) / statistics.stdev(active) * math.sqrt(252)
    )


def test_ir_fails_closed_for_zero_tracking_error() -> None:
    with pytest.raises(ValueError, match="OOS_INFORMATION_RATIO_UNDEFINED"):
        compute_long_horizon_oos_metrics(
            strategy_session_returns=(0.01, 0.01),
            benchmark_session_returns=(0.0, 0.0),
            cost_1_5x_session_returns=(0.009, 0.009),
        )

