from datetime import UTC, date, datetime

import pytest

from us_intraday_lab.backtest.clock import BacktestClock


def test_clock_uses_official_xnys_minutes_and_preclose_boundary() -> None:
    clock = BacktestClock(
        session_date=date(2026, 7, 2),
        closeout_buffer_minutes=5,
    )

    assert len(clock.minutes) == 390
    assert clock.session_open == datetime(2026, 7, 2, 13, 30, tzinfo=UTC)
    assert clock.session_close == datetime(2026, 7, 2, 20, 0, tzinfo=UTC)
    assert clock.closeout_time == datetime(2026, 7, 2, 19, 55, tzinfo=UTC)
    assert clock.closeout_signal_time == datetime(2026, 7, 2, 19, 54, tzinfo=UTC)
    assert clock.is_official_minute(clock.session_open)
    assert not clock.is_official_minute(clock.session_close)


def test_clock_handles_xnys_early_close() -> None:
    clock = BacktestClock(
        session_date=date(2026, 11, 27),
        closeout_buffer_minutes=5,
    )

    assert len(clock.minutes) == 210
    assert clock.session_close == datetime(2026, 11, 27, 18, 0, tzinfo=UTC)
    assert clock.closeout_time == datetime(2026, 11, 27, 17, 55, tzinfo=UTC)


@pytest.mark.parametrize("value", [0, -1, 61, True, 1.5])
def test_clock_rejects_invalid_closeout_buffer(value: object) -> None:
    with pytest.raises((TypeError, ValueError), match="closeout_buffer_minutes"):
        BacktestClock(
            session_date=date(2026, 7, 2),
            closeout_buffer_minutes=value,  # type: ignore[arg-type]
        )
