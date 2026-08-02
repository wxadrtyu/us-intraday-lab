from datetime import date, timedelta

import pandas as pd
import pytest
from pydantic import ValidationError

from us_intraday_lab.contracts.validation import ChronologicalSplit
from us_intraday_lab.validation.splits import (
    FinalTestIsolationError,
    IsolatedChronologicalViews,
    create_chronological_split,
)


def _sessions(count: int) -> tuple[date, ...]:
    start = date(2026, 1, 1)
    return tuple(start + timedelta(days=index) for index in range(count))


def _bars(sessions: tuple[date, ...]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "session_date": [session for session in sessions for _symbol in ("SPY", "QQQ", "IWM")],
            "symbol": [symbol for _session in sessions for symbol in ("SPY", "QQQ", "IWM")],
            "close": list(range(len(sessions) * 3)),
        }
    )


def test_split_is_deterministic_chronological_and_records_rounding() -> None:
    sessions = _sessions(101)

    first = create_chronological_split(sessions, split_id="split-101")
    second = create_chronological_split(sessions, split_id="split-101")

    assert first == second
    assert len(first.train_sessions) / len(sessions) == pytest.approx(0.70, abs=0.02)
    assert len(first.validation_sessions) / len(sessions) == pytest.approx(0.20, abs=0.02)
    assert len(first.final_test_sessions) / len(sessions) == pytest.approx(0.10, abs=0.02)
    assert first.train_sessions[-1] < first.validation_sessions[0]
    assert first.validation_sessions[-1] < first.final_test_sessions[0]
    assert not set(first.train_sessions) & set(first.validation_sessions)
    assert not set(first.train_sessions) & set(first.final_test_sessions)
    assert not set(first.validation_sessions) & set(first.final_test_sessions)
    assert first.allocation_method == "largest_remainder_70_20_10"


@pytest.mark.parametrize(
    "sessions",
    [
        _sessions(9),
        (*_sessions(10), _sessions(10)[-1]),
        tuple(reversed(_sessions(10))),
    ],
)
def test_split_rejects_too_small_duplicate_or_unordered_sessions(
    sessions: tuple[date, ...],
) -> None:
    with pytest.raises(ValueError):
        create_chronological_split(sessions, split_id="invalid")


def test_split_contract_rejects_manual_non_70_20_10_allocation() -> None:
    sessions = _sessions(10)

    with pytest.raises(ValidationError, match="70/20/10"):
        ChronologicalSplit(
            split_id="bad-allocation",
            train_sessions=sessions[:5],
            validation_sessions=sessions[5:8],
            final_test_sessions=sessions[8:],
        )


def test_final_test_is_a_single_use_capability_after_selection_is_sealed() -> None:
    sessions = _sessions(20)
    split = create_chronological_split(sessions, split_id="split-20")
    views = IsolatedChronologicalViews(_bars(sessions), split)

    training = views.training_view()
    validation = views.validation_view()

    assert set(training["session_date"]) == set(split.train_sessions)
    assert set(validation["session_date"]) == set(split.validation_sessions)
    assert views.access_log == ("train", "validation")
    assert not hasattr(views, "final_test_view")

    evaluator = views.seal_selection()
    final_test = evaluator.final_test_view()
    assert set(final_test["session_date"]) == set(split.final_test_sessions)
    assert views.access_log == ("train", "validation", "final_test")

    with pytest.raises(FinalTestIsolationError, match="FINAL_TEST_ALREADY_CONSUMED"):
        evaluator.final_test_view()
    with pytest.raises(FinalTestIsolationError, match="FINAL_TEST_ALREADY_CONSUMED"):
        views.training_view()
    with pytest.raises(FinalTestIsolationError, match="FINAL_TEST_ALREADY_CONSUMED"):
        views.validation_view()


def test_views_reject_rows_outside_the_declared_split() -> None:
    sessions = _sessions(10)
    split = create_chronological_split(sessions, split_id="split-10")
    bars = _bars(sessions)
    bars.loc[len(bars)] = [date(2027, 1, 1), "SPY", 1.0]

    with pytest.raises(ValueError, match="outside the chronological split"):
        IsolatedChronologicalViews(bars, split)


def test_views_reject_missing_declared_sessions() -> None:
    sessions = _sessions(10)
    split = create_chronological_split(sessions, split_id="split-10")

    with pytest.raises(ValueError, match="exactly cover"):
        IsolatedChronologicalViews(_bars(sessions[:-1]), split)
