from datetime import date, timedelta

import pandas as pd
import pytest

from us_intraday_lab.portfolio_research import (
    evaluate_frozen_portfolio,
    null_distributions,
    slice_evaluation,
)

PARAMETERS = [
    [45, 300, 3, 1.5, 0.005, 0.02],
    [60, 360, 3, "spy_down", 0.003],
    0.25,
]


def _features() -> pd.DataFrame:
    rows = []
    sessions = [date(2025, 1, 2) + timedelta(days=index) for index in range(30)]
    for session_index, session in enumerate(sessions):
        for symbol in ("A", "B"):
            day_open = 100.0
            close_45 = 100.0
            close_60 = 101.0
            close_30 = 100.0
            volume = 100.0
            vwap = 100.0
            high = 101.0
            low = 99.0
            open_300 = 100.0
            open_360 = 100.0
            spy_45 = 0.0
            spy_60 = 0.001
            spy_300 = 0.0
            spy_360 = 0.0
            if session_index == 25 and symbol == "A":
                close_45 = 103.0
                volume = 200.0
                vwap = 102.0
                high = 103.0
                open_300 = 110.0
                spy_45 = 0.005
                spy_60 = 0.005
                spy_300 = 0.015
                spy_360 = 0.015
            if session_index == 25 and symbol == "B":
                spy_45 = 0.005
                spy_60 = 0.005
                spy_300 = 0.015
                spy_360 = 0.015
            if session_index == 26:
                spy_45 = -0.001
                spy_60 = -0.001
                spy_300 = -0.002
                spy_360 = -0.002
                if symbol == "B":
                    close_30 = 98.5
                    close_60 = 99.0
                    open_360 = 105.0
            rows.append(
                {
                    "symbol": symbol,
                    "session_date": session,
                    "day_open": day_open,
                    "day_close": 100.0,
                    "close_30": close_30,
                    "close_45": close_45,
                    "close_60": close_60,
                    "open_46": 100.0,
                    "open_61": 100.0,
                    "open_300": open_300,
                    "open_330": 100.0,
                    "open_360": open_360,
                    "vwap_45": vwap,
                    "cum_volume_45": volume,
                    "range_high_45": high,
                    "range_low_45": low,
                    "spy_current_45": spy_45,
                    "spy_current_60": spy_60,
                    "spy_current_300": spy_300,
                    "spy_current_330": spy_300,
                    "spy_current_360": spy_360,
                }
            )
    return pd.DataFrame(rows)


def test_frozen_portfolio_matches_signal_times_and_caps_dynamic_allocation() -> None:
    evaluation = evaluate_frozen_portfolio(_features(), PARAMETERS, round_trip_cost=0.0009)

    assert evaluation.trade_count == 2
    assert evaluation.session_returns[25] == pytest.approx(0.0991)
    assert evaluation.session_returns[26] == pytest.approx(0.0491)
    assert sum(evaluation.session_returns[:25]) == 0.0
    assert evaluation.components.sum(axis=1).max() == pytest.approx(0.0991)


def test_portfolio_slice_and_null_distributions_are_deterministic() -> None:
    evaluation = evaluate_frozen_portfolio(_features(), PARAMETERS, round_trip_cost=0.0009)
    sessions = evaluation.sessions[20:]
    sliced = slice_evaluation(evaluation, sessions)

    assert sliced.round_trip_cost == evaluation.round_trip_cost

    first = null_distributions(sliced, repetitions=100, seed=7, round_trip_cost=0.0009)
    second = null_distributions(sliced, repetitions=100, seed=7, round_trip_cost=0.0009)

    assert sliced.trade_count == 2
    assert first == second
    assert set(first) == {"SESSION_SIGNAL_PERMUTATION", "SESSION_CIRCULAR_SHIFT"}
