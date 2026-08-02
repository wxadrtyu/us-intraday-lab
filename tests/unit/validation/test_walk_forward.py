from datetime import date, timedelta

import pytest

from us_intraday_lab.validation.walk_forward import (
    WalkForwardWindow,
    build_walk_forward_windows,
    record_walk_forward_result,
)


def _sessions(count: int) -> tuple[date, ...]:
    start = date(2026, 1, 1)
    return tuple(start + timedelta(days=index) for index in range(count))


def test_walk_forward_windows_are_rolling_chronological_and_session_aligned() -> None:
    sessions = _sessions(30)

    windows = build_walk_forward_windows(
        sessions,
        train_size=10,
        evaluation_size=5,
        step_size=5,
    )

    assert len(windows) == 4
    assert windows[0].train_sessions == sessions[:10]
    assert windows[0].evaluation_sessions == sessions[10:15]
    assert windows[1].train_sessions == sessions[5:15]
    assert windows[1].evaluation_sessions == sessions[15:20]
    for window in windows:
        assert window.train_sessions[-1] < window.evaluation_sessions[0]
        assert not set(window.train_sessions) & set(window.evaluation_sessions)


def test_walk_forward_result_records_boundaries_and_base_net_return() -> None:
    window = build_walk_forward_windows(
        _sessions(15),
        train_size=10,
        evaluation_size=5,
        step_size=5,
    )[0]

    result = record_walk_forward_result(
        window,
        strategy_id="strategy-1",
        base_net_return=0.0125,
    )

    assert result.window_id == window.window_id
    assert result.train_start == window.train_sessions[0]
    assert result.train_end == window.train_sessions[-1]
    assert result.validation_start == window.evaluation_sessions[0]
    assert result.validation_end == window.evaluation_sessions[-1]
    assert result.metrics_by_cost_scenario["base"]["net_return"] == pytest.approx(0.0125)


@pytest.mark.parametrize(
    ("train_size", "evaluation_size", "step_size"),
    [(0, 5, 5), (10, 0, 5), (10, 5, 0), (True, 5, 5)],
)
def test_walk_forward_rejects_invalid_window_sizes(
    train_size: object,
    evaluation_size: object,
    step_size: object,
) -> None:
    with pytest.raises((TypeError, ValueError)):
        build_walk_forward_windows(
            _sessions(30),
            train_size=train_size,  # type: ignore[arg-type]
            evaluation_size=evaluation_size,  # type: ignore[arg-type]
            step_size=step_size,  # type: ignore[arg-type]
        )


def test_walk_forward_contract_rejects_overlapping_manual_window() -> None:
    sessions = _sessions(10)

    with pytest.raises(ValueError, match="chronological and disjoint"):
        WalkForwardWindow(
            window_id="forged",
            train_sessions=sessions[:7],
            evaluation_sessions=sessions[6:],
        )
