from datetime import date

from us_intraday_lab.data.calendar import expected_minute_index


def test_xnys_regular_session_has_390_minutes() -> None:
    index = expected_minute_index(date(2026, 7, 2))

    assert len(index) == 390
    assert str(index.tz) == "UTC"
    assert index[0].isoformat() == "2026-07-02T13:30:00+00:00"
    assert index[-1].isoformat() == "2026-07-02T19:59:00+00:00"


def test_xnys_half_day_uses_official_early_close() -> None:
    index = expected_minute_index(date(2026, 11, 27))

    assert len(index) == 210
    assert index[0].isoformat() == "2026-11-27T14:30:00+00:00"
    assert index[-1].isoformat() == "2026-11-27T17:59:00+00:00"
