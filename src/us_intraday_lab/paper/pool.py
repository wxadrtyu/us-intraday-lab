"""Frozen v247/v449 account-level Alpaca Paper allocation."""

from __future__ import annotations

from datetime import date
from typing import Literal, cast

import numpy as np
import pandas as pd

from us_intraday_lab.paper.v449 import SleeveSignal, _volatility_exposure
from us_intraday_lab.v45_research_shadow import (
    EXIT_BAR,
    HORIZONS,
    _bucket,
    _prior20,
    _raw_return,
    _signal,
)
from us_intraday_lab.v247_research_shadow import (
    COMPONENT_DECISION,
    COMPONENT_EXIT,
    COMPONENT_WEIGHT,
    _component_raw_return,
    _component_signal,
)

V247_ID = "lev-v247-df683b8a37c927f6"
V449_ID = "lev-v449-03e9e3f9c4b21390"
POOL_ALLOCATIONS = {V247_ID: 0.5, V449_ID: 0.5}
ANCHOR_WEIGHT = 0.95
V247_TARGET_VOLATILITY = 0.30


def _exposure(raw_history: list[float], target: float) -> float:
    realized = float(np.std(raw_history, ddof=1) * np.sqrt(252.0))
    return min(1.0, target / realized) if realized > 1e-8 else 1.0


def v247_signals_at(
    bars: pd.DataFrame, *, session_date: date, decision_bar: int
) -> tuple[SleeveSignal, ...]:
    """Evaluate frozen v247 signals using only bars available at the decision."""

    buckets, sessions, _ = _bucket(bars)
    if session_date not in sessions:
        raise ValueError("V247_TARGET_SESSION_ABSENT")
    target_index = sessions.index(session_date)
    if target_index < 35:
        raise ValueError("V247_REQUIRES_35_PRIOR_SESSIONS")
    prior = _prior20(buckets, sessions)
    signals: list[SleeveSignal] = []
    if decision_bar == COMPONENT_DECISION:
        component_symbol = _component_signal(buckets, session_date)
        if component_symbol is not None:
            raw = [
                _component_raw_return(buckets, sessions[index], cost=0.0009, delay=0)[0]
                for index in range(target_index - 15, target_index)
            ]
            signals.append(
                SleeveSignal(
                    sleeve="component",
                    symbol=cast(Literal["TQQQ", "SOXL"], component_symbol),
                    decision_bar=decision_bar,
                    exit_bar=COMPONENT_EXIT,
                    weight=COMPONENT_WEIGHT,
                    exposure=_exposure(raw, V247_TARGET_VOLATILITY),
                )
            )
    if decision_bar in HORIZONS:
        anchor_symbol, selected_at = _signal(buckets, session_date, prior.iloc[target_index])
        if anchor_symbol is not None and selected_at == decision_bar:
            raw = [
                _raw_return(buckets, sessions[index], prior.iloc[index], cost=0.0009, delay=0)[0]
                for index in range(target_index - 15, target_index)
            ]
            signals.append(
                SleeveSignal(
                    sleeve="anchor",
                    symbol=cast(Literal["TQQQ", "SOXL"], anchor_symbol),
                    decision_bar=decision_bar,
                    exit_bar=EXIT_BAR,
                    weight=ANCHOR_WEIGHT,
                    exposure=_volatility_exposure(raw),
                )
            )
    return tuple(signals)


def validate_pool_allocations() -> None:
    if set(POOL_ALLOCATIONS) != {V247_ID, V449_ID}:
        raise ValueError("PAPER_POOL_MEMBERSHIP_MISMATCH")
    if not np.isclose(sum(POOL_ALLOCATIONS.values()), 1.0):
        raise ValueError("PAPER_POOL_ALLOCATION_SUM_MISMATCH")
    if any(weight <= 0.0 for weight in POOL_ALLOCATIONS.values()):
        raise ValueError("PAPER_POOL_ALLOCATION_NONPOSITIVE")
