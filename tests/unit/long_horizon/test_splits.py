from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from us_intraday_lab.long_horizon.splits import (
    LongHorizonSplit,
    create_long_horizon_split,
)


def test_long_horizon_split_is_deterministic_60_20_20() -> None:
    sessions = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(300))

    split = create_long_horizon_split(sessions, split_id="split-a")

    assert len(split.train_sessions) == 180
    assert len(split.validation_sessions) == 60
    assert len(split.final_test_sessions) == 60
    assert split.oos_sessions == split.validation_sessions + split.final_test_sessions
    assert create_long_horizon_split(sessions, split_id="split-a") == split


def test_split_fails_when_oos_is_too_short() -> None:
    sessions = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(200))

    with pytest.raises(ValueError, match="MINIMUM_LONG_HORIZON_OOS_NOT_MET"):
        create_long_horizon_split(sessions, split_id="too-short")


def test_split_fails_when_final_is_too_short() -> None:
    sessions = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(250))

    with pytest.raises(ValueError, match="MINIMUM_LONG_HORIZON_FINAL_NOT_MET"):
        create_long_horizon_split(sessions, split_id="too-short")


def test_split_contract_rejects_non_chronological_or_wrong_allocation() -> None:
    sessions = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(300))
    split = create_long_horizon_split(sessions, split_id="split-a")

    with pytest.raises(ValidationError, match="deterministic 60/20/20"):
        LongHorizonSplit(
            split_id="invalid",
            train_sessions=split.train_sessions[:-1],
            validation_sessions=(split.train_sessions[-1], *split.validation_sessions),
            final_test_sessions=split.final_test_sessions,
        )

