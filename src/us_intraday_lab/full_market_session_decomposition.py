"""Frozen full-market daily overnight/intraday decomposition contract."""

from __future__ import annotations

from dataclasses import dataclass

FAMILIES = (
    "persistent_overnight_drift",
    "overnight_underreaction",
    "persistent_intraday_drift",
    "gap_reversal_quality",
    "session_divergence",
)
LOOKBACKS = (20, 42, 63, 126)
REFRESH_LIFE_PAIRS = ((1, 1), (5, 5), (5, 10), (10, 10), (21, 21))
TOP_COUNTS = (10, 20, 40, 80)


@dataclass(frozen=True, slots=True)
class Specification:
    family: str
    lookback: int
    refresh_sessions: int
    life_sessions: int
    top_count: int


def specifications() -> tuple[Specification, ...]:
    """Return the immutable 400-cell session-decomposition grid."""
    result = tuple(
        Specification(family, lookback, refresh, life, top_count)
        for family in FAMILIES
        for lookback in LOOKBACKS
        for refresh, life in REFRESH_LIFE_PAIRS
        for top_count in TOP_COUNTS
    )
    if len(result) != 400 or len(set(result)) != 400:
        raise AssertionError("FULL_MARKET_SESSION_GRID_INVALID")
    return result

