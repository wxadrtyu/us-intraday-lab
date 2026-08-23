"""Frozen v247/v449/v798 account-level Alpaca Paper allocation."""

from __future__ import annotations

from datetime import date
from typing import Literal, cast

import numpy as np
import pandas as pd

from us_intraday_lab.paper.v449 import SleeveSignal, _volatility_exposure
from us_intraday_lab.v45_research_shadow import (
    EXIT_BAR,
    HORIZONS,
    SYMBOLS,
    _bucket,
    _prior20,
    _raw_return,
    _signal,
    _value,
)
from us_intraday_lab.v247_research_shadow import (
    COMPONENT_DECISION,
    COMPONENT_EXIT,
    COMPONENT_WEIGHT,
    _component_raw_return,
    _component_signal,
)
from us_intraday_lab.v449_research_shadow import (
    _component_raw_return as _v449_component_raw_return,
)
from us_intraday_lab.v449_research_shadow import _component_signal as _v449_component_signal

V247_ID = "lev-v247-df683b8a37c927f6"
V449_ID = "lev-v449-03e9e3f9c4b21390"
V798_ID = "lev-v798-d0612cdc630bb224"
POOL_ALLOCATIONS = {V247_ID: 1.0 / 3.0, V449_ID: 1.0 / 3.0, V798_ID: 1.0 / 3.0}
ANCHOR_WEIGHT = 0.95
V247_TARGET_VOLATILITY = 0.30
V798_ANCHOR_WEIGHT = 0.90
V798_COMPONENT_WEIGHT = 0.10
V798_STATE_THRESHOLD = -0.7669704203418132
V798_STATE_STATS = {
    "spy_current": (0.00025614195953023374, 0.010253113582875267, 1.0),
    "sector_breadth": (0.4795862819814915, 0.32709697149548767, 1.0),
    "risk_asset_agreement": (0.5229540918163673, 0.44149242134531164, 1.0),
    "spy_volatility": (0.008505562032917743, 0.00398182785975375, -1.0),
}
SECTORS = ("XLB", "XLC", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY")


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


def v798_state_score(bars: pd.DataFrame, *, session_date: date) -> float:
    """Reproduce v798's frozen prior-close four-factor state score."""

    buckets, sessions, _ = _bucket(bars)
    if session_date not in sessions:
        raise ValueError("V798_TARGET_SESSION_ABSENT")
    target_index = sessions.index(session_date)
    if target_index < 1:
        raise ValueError("V798_PRIOR_SESSION_ABSENT")
    prior_session = sessions[target_index - 1]
    current: dict[str, float] = {}
    for symbol in SYMBOLS:
        opening = _value(buckets, prior_session, symbol, 0, "open")
        closing = _value(buckets, prior_session, symbol, 77, "close")
        first = _value(buckets, prior_session, symbol, 0, "first")
        last = _value(buckets, prior_session, symbol, 77, "last")
        current[symbol] = (
            closing / opening - 1.0
            if first == 0 and last == 389 and opening > 0 and np.isfinite(closing)
            else float("nan")
        )
    spy_bar_returns = np.asarray(
        [
            _value(buckets, prior_session, "SPY", bar, "close")
            / _value(buckets, prior_session, "SPY", bar, "open")
            - 1.0
            for bar in range(78)
        ],
        dtype=float,
    )
    spy_bar_returns = np.where(np.isfinite(spy_bar_returns), spy_bar_returns, 0.0)
    if not np.isfinite(current["SPY"]):
        raise ValueError("V798_PRIOR_SESSION_SPY_BOUNDARY_INVALID")
    factors = {
        "spy_current": current["SPY"],
        "sector_breadth": float(np.mean([current[symbol] > 0.0 for symbol in SECTORS])),
        "risk_asset_agreement": float(
            np.mean([current[symbol] > 0.0 for symbol in ("SPY", "QQQ", "IWM")])
        ),
        "spy_volatility": float(np.sqrt(np.sum(spy_bar_returns**2))),
    }
    pieces = [
        direction * (factors[name] - mean) / scale
        for name, (mean, scale, direction) in V798_STATE_STATS.items()
    ]
    return float(np.mean(pieces))


def v798_signals_at(
    bars: pd.DataFrame, *, session_date: date, decision_bar: int
) -> tuple[SleeveSignal, ...]:
    """Evaluate v798's frozen v45 anchor and prior-close-routed v449 component."""

    buckets, sessions, _ = _bucket(bars)
    if session_date not in sessions:
        raise ValueError("V798_TARGET_SESSION_ABSENT")
    target_index = sessions.index(session_date)
    if target_index < 35:
        raise ValueError("V798_REQUIRES_35_PRIOR_SESSIONS")
    prior = _prior20(buckets, sessions)
    signals: list[SleeveSignal] = []
    if decision_bar == COMPONENT_DECISION and v798_state_score(
        bars, session_date=session_date
    ) >= V798_STATE_THRESHOLD:
        component_symbol = _v449_component_signal(buckets, session_date)
        if component_symbol is not None:
            raw = [
                _v449_component_raw_return(
                    buckets, sessions[index], cost=0.0009, delay=0
                )[0]
                for index in range(target_index - 15, target_index)
            ]
            signals.append(
                SleeveSignal(
                    sleeve="component",
                    symbol=cast(Literal["TQQQ", "SOXL"], component_symbol),
                    decision_bar=decision_bar,
                    exit_bar=COMPONENT_EXIT,
                    weight=V798_COMPONENT_WEIGHT,
                    exposure=_volatility_exposure(raw),
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
                    weight=V798_ANCHOR_WEIGHT,
                    exposure=_volatility_exposure(raw),
                )
            )
    return tuple(signals)


def validate_pool_allocations() -> None:
    if set(POOL_ALLOCATIONS) != {V247_ID, V449_ID, V798_ID}:
        raise ValueError("PAPER_POOL_MEMBERSHIP_MISMATCH")
    if not np.isclose(sum(POOL_ALLOCATIONS.values()), 1.0):
        raise ValueError("PAPER_POOL_ALLOCATION_SUM_MISMATCH")
    if any(weight <= 0.0 for weight in POOL_ALLOCATIONS.values()):
        raise ValueError("PAPER_POOL_ALLOCATION_NONPOSITIVE")
