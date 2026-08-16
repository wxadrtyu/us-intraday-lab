"""Pure, brokerless prospective evaluator for the frozen v247 ensemble."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from us_intraday_lab.v45_research_shadow import (
    ASSETS,
    V45ShadowObservation,
    _bucket,
    _value,
    evaluate_v45_shadow_session,
)

ANCHOR_WEIGHT = 0.95
COMPONENT_WEIGHT = 0.05
COMPONENT_DECISION = 23
COMPONENT_CONFIRMATION = 20
COMPONENT_EXIT = 65
COMPONENT_THRESHOLD = 0.00013627469771827725
COMPONENT_MEAN = np.array(
    (
        -0.0010134654401263222,
        0.0005197268917250488,
        -0.035150778287138175,
        -0.3606876629952821,
        -0.0019137858280666342,
    )
)
COMPONENT_SCALE = np.array(
    (
        0.031849623316607685,
        0.012246958169044392,
        0.2735289328405527,
        0.4505291561061858,
        0.3104053610339678,
    )
)
COMPONENT_COEFFICIENTS = np.array(
    (
        0.0005720636435718803,
        -0.0001661007468131936,
        -0.00045086124057231087,
        -0.00029731729140655515,
        -0.000006274777378043453,
    )
)


@dataclass(frozen=True, slots=True)
class V247ShadowObservation:
    session_date: date
    anchor: V45ShadowObservation
    component_selected_symbol: str | None
    component_exposure: float
    component_standard_return: float
    component_cost_18bp_return: float
    component_delay_5min_return: float
    component_benchmark_return: float

    @property
    def standard_return(self) -> float:
        return (
            ANCHOR_WEIGHT * self.anchor.standard_return
            + COMPONENT_WEIGHT * self.component_standard_return
        )

    @property
    def cost_18bp_return(self) -> float:
        return (
            ANCHOR_WEIGHT * self.anchor.cost_18bp_return
            + COMPONENT_WEIGHT * self.component_cost_18bp_return
        )

    @property
    def delay_5min_return(self) -> float:
        return (
            ANCHOR_WEIGHT * self.anchor.delay_5min_return
            + COMPONENT_WEIGHT * self.component_delay_5min_return
        )

    @property
    def benchmark_return(self) -> float:
        return (
            ANCHOR_WEIGHT * self.anchor.benchmark_return
            + COMPONENT_WEIGHT * self.component_benchmark_return
        )

    def as_record(self) -> dict[str, object]:
        return {
            "schema_version": "1.0.0",
            "candidate_id": "lev-v247-df683b8a37c927f6",
            "provider": "alpaca",
            "feed": "iex",
            "session_date": self.session_date.isoformat(),
            "weights": {"v45_anchor": ANCHOR_WEIGHT, "component": COMPONENT_WEIGHT},
            "signals": {
                "anchor_symbol": self.anchor.selected_symbol,
                "anchor_decision_bar": self.anchor.decision_bar,
                "anchor_exposure": self.anchor.exposure,
                "component_symbol": self.component_selected_symbol,
                "component_decision_bar": (
                    COMPONENT_DECISION if self.component_selected_symbol is not None else None
                ),
                "component_exposure": self.component_exposure,
            },
            "theoretical": {
                "standard_9bp_return": self.standard_return,
                "cost_18bp_return": self.cost_18bp_return,
                "delay_5min_9bp_return": self.delay_5min_return,
                "benchmark_return": self.benchmark_return,
            },
            "quality": {
                "context_sessions": self.anchor.context_sessions,
                "target_minimum_minutes": self.anchor.target_minimum_minutes,
            },
            "admission": {
                "type": "USER_AUTHORIZED_RESEARCH_SHADOW_EXCEPTION",
                "inherited_v45_factory_null_passed": False,
                "component_factory_null_passed": True,
                "global_bonferroni_passed": False,
            },
        }


def _component_features(
    buckets: pd.DataFrame, session: date, symbol: str, decision: int
) -> np.ndarray:
    opening = _value(buckets, session, symbol, 0, "open")
    closing = _value(buckets, session, symbol, decision, "close")
    previous = max(0, decision - 6)
    recent_base = _value(buckets, session, symbol, previous, "close")
    bar_returns = np.array(
        [
            _value(buckets, session, symbol, bar, "close")
            / _value(buckets, session, symbol, bar, "open")
            - 1.0
            for bar in range(decision + 1)
        ]
    )
    volumes = np.array(
        [_value(buckets, session, symbol, bar, "volume") for bar in range(decision + 1)]
    )
    if not np.isfinite(bar_returns).all() or not np.isfinite(volumes).all():
        return np.full(5, np.nan)
    path = float(np.abs(bar_returns).sum())
    split = max(1, decision - 2)
    earlier_volume = float(np.mean(volumes[:split]))
    recent_volume = float(np.mean(volumes[split : decision + 1]))
    total_volume = float(volumes.sum())
    return np.array(
        (
            closing / opening - 1.0 if opening > 0 else math.nan,
            closing / recent_base - 1.0 if recent_base > 0 else math.nan,
            (
                float(np.sum(np.sign(bar_returns) * volumes)) / total_volume
                if total_volume > 0
                else math.nan
            ),
            recent_volume / earlier_volume - 1.0 if earlier_volume > 0 else math.nan,
            (closing / opening - 1.0) / path if opening > 0 and path > 1e-8 else math.nan,
        )
    )


def _component_scores(buckets: pd.DataFrame, session: date, decision: int) -> dict[str, float]:
    output = {}
    for symbol in ASSETS:
        features = _component_features(buckets, session, symbol, decision)
        if np.isfinite(features).all():
            output[symbol] = float(
                np.sum(((features - COMPONENT_MEAN) / COMPONENT_SCALE) * COMPONENT_COEFFICIENTS)
            )
    return output


def _component_signal(buckets: pd.DataFrame, session: date) -> str | None:
    current = _component_scores(buckets, session, COMPONENT_DECISION)
    earlier = _component_scores(buckets, session, COMPONENT_CONFIRMATION)
    if not current or not earlier:
        return None
    selected = max(current, key=current.__getitem__)
    earlier_selected = max(earlier, key=earlier.__getitem__)
    if (
        selected == earlier_selected
        and current[selected] >= COMPONENT_THRESHOLD
        and earlier[selected] >= COMPONENT_THRESHOLD
    ):
        return selected
    return None


def _component_raw_return(
    buckets: pd.DataFrame,
    session: date,
    *,
    cost: float,
    delay: int,
    strict: bool = False,
) -> tuple[float, float, str | None]:
    symbol = _component_signal(buckets, session)
    if symbol is None:
        return 0.0, 0.0, None
    entry_bar = COMPONENT_DECISION + 1 + delay
    entry = _value(buckets, session, symbol, entry_bar, "open")
    exit_price = _value(buckets, session, symbol, COMPONENT_EXIT, "open")
    spy_entry = _value(buckets, session, "SPY", entry_bar, "open")
    spy_exit = _value(buckets, session, "SPY", COMPONENT_EXIT, "open")
    if not all(np.isfinite((entry, exit_price, spy_entry, spy_exit))) or min(entry, spy_entry) <= 0:
        if strict:
            raise ValueError("v247 component is missing an exact entry or exit bar")
        return 0.0, 0.0, None
    return exit_price / entry - 1.0 - cost, spy_exit / spy_entry - 1.0, symbol


def evaluate_v247_shadow_session(
    bars: pd.DataFrame, *, session_date: date
) -> V247ShadowObservation:
    anchor = evaluate_v45_shadow_session(bars, session_date=session_date)
    buckets, sessions, _ = _bucket(bars)
    target_index = sessions.index(session_date)
    raw_history = [
        _component_raw_return(buckets, sessions[index], cost=0.0009, delay=0)[0]
        for index in range(target_index - 15, target_index)
    ]
    realized = float(np.std(raw_history, ddof=1) * np.sqrt(252.0))
    exposure = min(1.0, 0.30 / realized) if np.isfinite(realized) and realized > 1e-8 else 1.0
    standard, benchmark, symbol = _component_raw_return(
        buckets, session_date, cost=0.0009, delay=0, strict=True
    )
    stressed, _, _ = _component_raw_return(buckets, session_date, cost=0.0018, delay=0, strict=True)
    delayed, _, _ = _component_raw_return(buckets, session_date, cost=0.0009, delay=1, strict=True)
    return V247ShadowObservation(
        session_date=session_date,
        anchor=anchor,
        component_selected_symbol=symbol,
        component_exposure=exposure,
        component_standard_return=standard * exposure,
        component_cost_18bp_return=stressed * exposure,
        component_delay_5min_return=delayed * exposure,
        component_benchmark_return=benchmark * exposure,
    )
