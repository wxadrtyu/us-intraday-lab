"""Pure, brokerless prospective evaluator for the frozen v45 strategy."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from us_intraday_lab.research_shadow_alpaca import NEW_YORK

SYMBOLS = (
    "SPY",
    "QQQ",
    "IWM",
    "TQQQ",
    "SOXL",
    "XLB",
    "XLC",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLRE",
    "XLU",
    "XLV",
    "XLY",
)
ASSETS = ("TQQQ", "SOXL")
HORIZONS = (20, 23, 26, 29)
EXIT_BAR = 72
THRESHOLD = 0.75
DIRECTION = np.array((1.0, -1.0, -1.0, -1.0))
RELIABILITY = np.array(
    (0.005062045102016475, 0.029985483037028183, 0.029948475740661222, 0.04944995965820357)
)
MODEL = {
    20: (
        (-0.00026689749028793947, -0.27813620546570883, 0.5090047003649946, 0.022264580682253468),
        (0.02987346203686809, 0.5344938401448129, 0.43368167952385017, 0.1944322483490903),
    ),
    23: (
        (-0.00014026304549405103, -0.3806546634176211, 0.5041977058474522, 0.020578371617836287),
        (0.030921266965561908, 0.4118273892737088, 0.4345965230785372, 0.19560688955937527),
    ),
    26: (
        (-0.0011337442772737223, -0.3325985504568435, 0.5057552037004092, 0.021690890109432707),
        (0.03266618182947731, 0.4802352913711748, 0.4418148109758646, 0.20104741860812161),
    ),
    29: (
        (0.0007826151903843548, -0.3614106349623662, 0.4836769271859246, 0.014985738905597313),
        (0.03405012808840988, 0.5296239194334035, 0.43438335463050676, 0.19436858090099846),
    ),
}


@dataclass(frozen=True, slots=True)
class V45ShadowObservation:
    session_date: date
    selected_symbol: str | None
    decision_bar: int | None
    exposure: float
    standard_return: float
    cost_18bp_return: float
    delay_5min_return: float
    benchmark_return: float
    context_sessions: int
    target_minimum_minutes: int

    def as_record(self) -> dict[str, object]:
        return {
            "schema_version": "1.0.0",
            "candidate_id": "lev-v45e-0d302fbf92727a31",
            "provider": "alpaca",
            "feed": "iex",
            "session_date": self.session_date.isoformat(),
            "signal": {
                "selected_symbol": self.selected_symbol,
                "decision_bar": self.decision_bar,
                "exposure": self.exposure,
            },
            "theoretical": {
                "standard_9bp_return": self.standard_return,
                "cost_18bp_return": self.cost_18bp_return,
                "delay_5min_9bp_return": self.delay_5min_return,
                "benchmark_return": self.benchmark_return,
            },
            "quality": {
                "context_sessions": self.context_sessions,
                "target_minimum_minutes": self.target_minimum_minutes,
            },
            "admission": {
                "type": "USER_AUTHORIZED_RESEARCH_SHADOW_EXCEPTION",
                "factory_null_passed": False,
            },
        }


def _bucket(frame: pd.DataFrame) -> tuple[pd.DataFrame, tuple[date, ...], pd.Series]:
    required = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        raise ValueError("v45 research shadow bars have an invalid schema")
    data = frame.loc[:, list(required)].copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
    localized = data["timestamp"].dt.tz_convert(NEW_YORK)
    data["session_date"] = localized.dt.date
    data["minute"] = (localized.dt.hour - 9) * 60 + localized.dt.minute - 30
    data = data.loc[data["minute"].between(0, 389) & data["symbol"].isin(SYMBOLS)].copy()
    if data.duplicated(["symbol", "session_date", "minute"]).any():
        raise ValueError("v45 research shadow contains duplicate minutes")
    data["bar"] = (data["minute"] // 5).astype(int)
    grouped = data.sort_values("timestamp").groupby(["session_date", "symbol", "bar"])
    buckets = grouped.agg(
        open=("open", "first"),
        close=("close", "last"),
        volume=("volume", "sum"),
        count=("minute", "count"),
        first=("minute", "min"),
        last=("minute", "max"),
    )
    sessions = tuple(sorted(data["session_date"].unique()))
    counts = data.groupby(["session_date", "symbol"])["minute"].nunique()
    return buckets, sessions, counts


def _value(buckets: pd.DataFrame, session: date, symbol: str, bar: int, column: str) -> float:
    try:
        return float(buckets.loc[(session, symbol, bar), column])
    except KeyError:
        return math.nan


def _prior20(buckets: pd.DataFrame, sessions: tuple[date, ...]) -> pd.DataFrame:
    daily = pd.DataFrame(index=sessions, columns=SYMBOLS, dtype=float)
    for session in sessions:
        for symbol in SYMBOLS:
            opening = _value(buckets, session, symbol, 0, "open")
            closing = _value(buckets, session, symbol, 77, "close")
            first = _value(buckets, session, symbol, 0, "first")
            last = _value(buckets, session, symbol, 77, "last")
            if first == 0 and last == 389 and opening > 0 and np.isfinite(closing):
                daily.loc[session, symbol] = closing / opening - 1.0
    prior = pd.DataFrame(index=sessions, columns=SYMBOLS, dtype=float)
    for index in range(20, len(sessions)):
        window = daily.iloc[index - 20 : index]
        valid = window.notna().all(axis=0)
        prior.iloc[index, valid.to_numpy()] = (1.0 + window.loc[:, valid]).prod(axis=0) - 1.0
    return prior


def _signal(
    buckets: pd.DataFrame, session: date, prior: pd.Series
) -> tuple[str | None, int | None]:
    weights = RELIABILITY / RELIABILITY.sum()
    previous_symbol = None
    previous_above = False
    for decision in HORIZONS:
        scores = {}
        finite_prior = prior.loc[list(SYMBOLS[1:])].dropna().sort_values(kind="stable")
        ranks = (
            {
                symbol: rank / (len(finite_prior) - 1)
                for rank, symbol in enumerate(finite_prior.index)
            }
            if len(finite_prior) >= 2
            else {}
        )
        for symbol in ASSETS:
            opening = _value(buckets, session, symbol, 0, "open")
            closing = _value(buckets, session, symbol, decision, "close")
            volumes = np.array(
                [_value(buckets, session, symbol, bar, "volume") for bar in range(decision + 1)]
            )
            split = max(1, decision - 2)
            earlier = (
                float(np.mean(volumes[:split])) if np.isfinite(volumes[:split]).all() else math.nan
            )
            recent = (
                float(np.mean(volumes[split:])) if np.isfinite(volumes[split:]).all() else math.nan
            )
            volume_acceleration = recent / earlier - 1.0 if earlier > 0 else math.nan
            vector = np.array(
                (
                    closing / opening - 1.0 if opening > 0 else math.nan,
                    volume_acceleration,
                    ranks.get(symbol, math.nan),
                    float(prior.get(symbol, math.nan)),
                )
            )
            mean, scale = (np.asarray(value) for value in MODEL[decision])
            if np.isfinite(vector).all():
                scores[symbol] = float(np.sum(((vector - mean) / scale) * DIRECTION * weights))
        if not scores:
            previous_symbol, previous_above = None, False
            continue
        symbol = max(scores, key=scores.__getitem__)
        above = scores[symbol] >= THRESHOLD
        if above and previous_above and previous_symbol == symbol:
            return symbol, decision
        previous_symbol, previous_above = symbol, above
    return None, None


def _raw_return(
    buckets: pd.DataFrame,
    session: date,
    prior: pd.Series,
    cost: float,
    delay: int,
    *,
    strict: bool = False,
) -> tuple[float, float, str | None, int | None]:
    symbol, decision = _signal(buckets, session, prior)
    if symbol is None or decision is None:
        return 0.0, 0.0, None, None
    entry_bar = decision + 1 + delay
    entry = _value(buckets, session, symbol, entry_bar, "open")
    exit_price = _value(buckets, session, symbol, EXIT_BAR, "open")
    spy_entry = _value(buckets, session, "SPY", entry_bar, "open")
    spy_exit = _value(buckets, session, "SPY", EXIT_BAR, "open")
    if not all(np.isfinite((entry, exit_price, spy_entry, spy_exit))) or min(entry, spy_entry) <= 0:
        if strict:
            raise ValueError("v45 selected trade is missing an exact entry or exit bar")
        return 0.0, 0.0, None, None
    return exit_price / entry - 1.0 - cost, spy_exit / spy_entry - 1.0, symbol, decision


def evaluate_v45_shadow_session(bars: pd.DataFrame, *, session_date: date) -> V45ShadowObservation:
    buckets, sessions, counts = _bucket(bars)
    if session_date not in sessions:
        raise ValueError("v45 target session is absent")
    target_index = sessions.index(session_date)
    if target_index < 35:
        raise ValueError("v45 research shadow requires at least 35 prior sessions")
    target_counts = counts.loc[session_date].reindex(SYMBOLS)
    if target_counts.isna().any():
        raise ValueError("v45 target session is missing a required symbol")
    prior = _prior20(buckets, sessions)
    raw_history = []
    for index in range(target_index - 15, target_index):
        value, _, _, _ = _raw_return(
            buckets, sessions[index], prior.iloc[index], cost=0.0009, delay=0
        )
        raw_history.append(value)
    realized = float(np.std(raw_history, ddof=1) * np.sqrt(252.0))
    exposure = min(1.0, 0.35 / realized) if np.isfinite(realized) and realized > 1e-8 else 1.0
    standard, benchmark, symbol, decision = _raw_return(
        buckets,
        session_date,
        prior.iloc[target_index],
        cost=0.0009,
        delay=0,
        strict=True,
    )
    stressed, _, _, _ = _raw_return(
        buckets,
        session_date,
        prior.iloc[target_index],
        cost=0.0018,
        delay=0,
        strict=True,
    )
    delayed, _, _, _ = _raw_return(
        buckets,
        session_date,
        prior.iloc[target_index],
        cost=0.0009,
        delay=1,
        strict=True,
    )
    return V45ShadowObservation(
        session_date=session_date,
        selected_symbol=symbol,
        decision_bar=decision,
        exposure=exposure,
        standard_return=standard * exposure,
        cost_18bp_return=stressed * exposure,
        delay_5min_return=delayed * exposure,
        benchmark_return=benchmark * exposure,
        context_sessions=target_index,
        target_minimum_minutes=int(target_counts.min()),
    )
