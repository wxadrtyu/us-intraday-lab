from __future__ import annotations

from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

_WEIGHTS = (6, 2, 2)
_MAX_SESSIONS = 100_000


def long_horizon_split_counts(total: int) -> tuple[int, int, int]:
    """Allocate exact deterministic counts with largest remainders and stable ties."""

    if type(total) is not int:
        raise TypeError("total must be an exact integer")
    if not 1 <= total <= _MAX_SESSIONS:
        raise ValueError(f"total must contain between 1 and {_MAX_SESSIONS} sessions")
    counts = [total * weight // sum(_WEIGHTS) for weight in _WEIGHTS]
    remainders = [total * weight % sum(_WEIGHTS) for weight in _WEIGHTS]
    order = sorted(range(3), key=lambda index: (-remainders[index], index))
    for index in order[: total - sum(counts)]:
        counts[index] += 1
    return counts[0], counts[1], counts[2]


class LongHorizonSplit(BaseModel):
    """Closed chronological 60/20/20 campaign split with minimum evidence floors."""

    model_config = ConfigDict(frozen=True, extra="forbid", revalidate_instances="always")

    schema_version: Literal["1.0.0"] = "1.0.0"
    split_id: str = Field(min_length=1)
    allocation_method: Literal["largest_remainder_60_20_20"] = (
        "largest_remainder_60_20_20"
    )
    train_sessions: tuple[date, ...] = Field(min_length=1, max_length=_MAX_SESSIONS)
    validation_sessions: tuple[date, ...] = Field(min_length=1, max_length=_MAX_SESSIONS)
    final_test_sessions: tuple[date, ...] = Field(min_length=1, max_length=_MAX_SESSIONS)

    @property
    def oos_sessions(self) -> tuple[date, ...]:
        return self.validation_sessions + self.final_test_sessions

    @model_validator(mode="after")
    def validate_split(self) -> Self:
        groups = (self.train_sessions, self.validation_sessions, self.final_test_sessions)
        if any(tuple(sorted(group)) != group or len(set(group)) != len(group) for group in groups):
            raise ValueError("split sessions must be sorted and unique")
        if not (
            self.train_sessions[-1]
            < self.validation_sessions[0]
            <= self.validation_sessions[-1]
            < self.final_test_sessions[0]
        ):
            raise ValueError("split sessions must be strictly chronological and disjoint")
        counts = tuple(len(group) for group in groups)
        if counts != long_horizon_split_counts(sum(counts)):
            raise ValueError("split sessions must use deterministic 60/20/20 allocation")
        if len(self.oos_sessions) < 90:
            raise ValueError("MINIMUM_LONG_HORIZON_OOS_NOT_MET")
        if len(self.final_test_sessions) < 60:
            raise ValueError("MINIMUM_LONG_HORIZON_FINAL_NOT_MET")
        return self


def create_long_horizon_split(
    sessions: tuple[date, ...],
    *,
    split_id: str,
) -> LongHorizonSplit:
    """Create the sole chronological split for one accepted campaign dataset."""

    if type(sessions) is not tuple:
        raise TypeError("sessions must be an exact tuple")
    if tuple(sorted(sessions)) != sessions or len(set(sessions)) != len(sessions):
        raise ValueError("sessions must be sorted and unique")
    train_count, validation_count, _final_count = long_horizon_split_counts(len(sessions))
    validation_end = train_count + validation_count
    return LongHorizonSplit(
        split_id=split_id,
        train_sessions=sessions[:train_count],
        validation_sessions=sessions[train_count:validation_end],
        final_test_sessions=sessions[validation_end:],
    )
