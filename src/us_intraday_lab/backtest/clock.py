"""Official XNYS minute clock and deterministic closeout boundaries."""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from us_intraday_lab.data.calendar import expected_minute_index

MAX_CLOSEOUT_BUFFER_MINUTES = 60


@dataclass(frozen=True, slots=True)
class BacktestClock:
    """One official regular session expressed as UTC minute-open timestamps."""

    session_date: date
    closeout_buffer_minutes: int
    minutes: tuple[datetime, ...] = field(init=False)
    session_open: datetime = field(init=False)
    session_close: datetime = field(init=False)
    closeout_time: datetime = field(init=False)
    closeout_signal_time: datetime = field(init=False)

    def __post_init__(self) -> None:
        if type(self.session_date) is not date:
            raise TypeError("session_date must be an exact date")
        if (
            type(self.closeout_buffer_minutes) is not int
            or not 1 <= self.closeout_buffer_minutes <= MAX_CLOSEOUT_BUFFER_MINUTES
        ):
            raise ValueError(
                "closeout_buffer_minutes must be an integer between 1 and "
                f"{MAX_CLOSEOUT_BUFFER_MINUTES}"
            )
        minutes = tuple(
            timestamp.to_pydatetime().astimezone(UTC)
            for timestamp in expected_minute_index(self.session_date)
        )
        if not minutes:
            raise ValueError("session_date must be an official XNYS session")
        session_close = minutes[-1] + timedelta(minutes=1)
        closeout_time = session_close - timedelta(minutes=self.closeout_buffer_minutes)
        closeout_signal_time = closeout_time - timedelta(minutes=1)
        if closeout_signal_time < minutes[0]:
            raise ValueError("closeout buffer leaves no eligible trading minute")
        object.__setattr__(self, "minutes", minutes)
        object.__setattr__(self, "session_open", minutes[0])
        object.__setattr__(self, "session_close", session_close)
        object.__setattr__(self, "closeout_time", closeout_time)
        object.__setattr__(self, "closeout_signal_time", closeout_signal_time)

    def is_official_minute(self, timestamp: datetime) -> bool:
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            return False
        return timestamp.astimezone(UTC) in self.minutes
