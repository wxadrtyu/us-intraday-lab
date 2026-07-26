from datetime import date

import exchange_calendars  # type: ignore[import-untyped]
import pandas as pd

_XNYS = exchange_calendars.get_calendar("XNYS")


def expected_minute_index(session_date: date) -> pd.DatetimeIndex:
    """Return every regular-session minute for an XNYS session in UTC."""
    session = pd.Timestamp(session_date)
    session_open = _XNYS.session_open(session)
    session_close = _XNYS.session_close(session)
    return pd.date_range(session_open, session_close, freq="min", inclusive="left")
