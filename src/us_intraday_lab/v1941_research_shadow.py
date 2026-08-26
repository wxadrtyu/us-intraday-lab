"""Frozen v1941 risk state and append-only, strictly brokerless observations."""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from us_intraday_lab.research_shadow_alpaca import NEW_YORK
from us_intraday_lab.v45_research_shadow import SYMBOLS, _bucket, _value

CANDIDATE_ID = "risk-v1941-d230dcf6cfea997c"
MEANS = dict(
    zip(
        ("sector_breadth", "sector_dispersion", "spy_current", "spy_volatility"),
        (0.3440391943385955, 0.005302562259683999, 1.3471753879822977e-05, 0.005021577569849581),
        strict=True,
    )
)
SCALES = dict(
    zip(
        MEANS,
        (0.22137022521104957, 0.002460973922747805, 0.005400720724141359, 0.0024230910024722555),
        strict=True,
    )
)
THRESHOLD = -0.3998694619090091
LABELS = {
    "candidate_id": CANDIDATE_ID,
    "order_route": "FORBIDDEN",
    "mode": "RESEARCH_SHADOW_NOT_PAPER_ADMISSION",
    "native_overlay_null_passed": False,
    "native_overlay_null_status": "NOT_COMPLETE",
    "inherited_v45_factory_null_passed": False,
    "global_bonferroni_passed": False,
    "source": "alpaca_iex_only",
}


def bar_time(session: date, bar: int) -> datetime:
    return (
        datetime.combine(session, time(9, 30), NEW_YORK) + timedelta(minutes=5 * bar)
    ).astimezone(UTC)


def through_bar(bars: pd.DataFrame, session: date, bar: int) -> pd.DataFrame:
    """Keep prior context but never expose an incomplete/future minute to a signal."""
    return bars.loc[pd.to_datetime(bars.timestamp, utc=True) < bar_time(session, bar + 1)]


def frozen_state(bars: pd.DataFrame, session: date) -> dict:
    buckets, _, _ = _bucket(through_bar(bars, session, 17))

    def current(symbol):
        opening = _value(buckets, session, symbol, 0, "open")
        close = _value(buckets, session, symbol, 17, "close")
        exact = (
            _value(buckets, session, symbol, 0, "first") == 0
            and _value(buckets, session, symbol, 17, "last") == 89
        )
        return close / opening - 1 if exact and opening > 0 else math.nan

    sectors = np.array([current(s) for s in SYMBOLS[5:]])
    finite = sectors[np.isfinite(sectors)]
    spy_returns = np.array(
        [
            _value(buckets, session, "SPY", i, "close") / _value(buckets, session, "SPY", i, "open")
            - 1
            for i in range(18)
        ]
    )
    # Preserve the research definition: missing sectors count false in breadth;
    # sparse internal SPY bars contribute zero to the squared-return sum.
    factors = {
        "sector_breadth": float(np.mean(sectors > 0)),
        "sector_dispersion": float(np.std(finite)) if len(finite) else math.nan,
        "spy_current": current("SPY"),
        "spy_volatility": float(np.sqrt(np.sum(spy_returns[np.isfinite(spy_returns)] ** 2))),
    }
    valid = all(math.isfinite(v) for v in factors.values())
    score = float(np.mean([(factors[n] - MEANS[n]) / SCALES[n] for n in MEANS]))
    return {
        "factors": {n: v if math.isfinite(v) else None for n, v in factors.items()},
        "score": score if valid else None,
        "budget_multiplier": (0.9 if score >= THRESHOLD else 0.45) if valid else 0.0,
        "available_sectors": len(finite),
        "state_valid": valid,
        "threshold": THRESHOLD,
        "state_bar": 17,
    }


def exact_open(bars: pd.DataFrame, session: date, symbol: str, minute: int) -> float:
    target = bar_time(session, 0) + timedelta(minutes=minute)
    values = bars.loc[
        (bars.symbol == symbol) & (pd.to_datetime(bars.timestamp, utc=True) == target), "open"
    ]
    if len(values) != 1 or not math.isfinite(float(values.iloc[0])) or values.iloc[0] <= 0:
        raise ValueError("EXACT_PRICE_UNAVAILABLE")
    return float(values.iloc[0])


def theoretical_results(
    bars: pd.DataFrame, session: date, signals: list[dict], multiplier: float, *, state_valid: bool
) -> dict:
    """Frozen signals only. Any missing fill invalidates that entire scenario."""
    results = {}
    for scenario, cost, delay in (
        ("9bp", 0.0009, 0),
        ("18bp", 0.0018, 0),
        ("delay_5min_9bp", 0.0009, 1),
        ("receipt_next_minute_9bp", 0.0009, 0),
    ):
        trades, missing = [], []
        for signal in signals:
            minute = (signal["decision_bar"] + 1 + delay) * 5
            if scenario == "receipt_next_minute_9bp":
                minute = signal["receipt_entry_minute"]
            try:
                entry = exact_open(bars, session, signal["symbol"], minute)
                close = exact_open(bars, session, signal["symbol"], signal["exit_bar"] * 5)
            except ValueError:
                missing.append({"sleeve": signal["sleeve"], "symbol": signal["symbol"]})
                continue
            gross = signal["weight"] * signal["exposure"]
            trades.append(
                {
                    **signal,
                    "entry_minute": minute,
                    "entry": entry,
                    "exit": close,
                    "baseline_return": gross * (close / entry - 1 - cost),
                    "candidate_return": gross * multiplier * (close / entry - 1 - cost),
                }
            )
        baseline = sum(t["baseline_return"] for t in trades) if not missing else None
        results[scenario] = {
            "status": "INCOMPLETE_PRICE" if missing else "COMPLETE",
            "v1254_raw_return": baseline,
            "v1254_common_state_return": baseline if state_valid else 0.0,
            "v1941_return": baseline * multiplier
            if baseline is not None
            else (0.0 if multiplier == 0 else None),
            "missing": missing,
            "trades": trades,
            "fill_type": "THEORETICAL_IEX_OPEN_NOT_BROKER_FILL",
        }
    return results


class ShadowLedger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.execute("PRAGMA journal_mode=WAL")
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                sequence INTEGER PRIMARY KEY, event_key TEXT NOT NULL UNIQUE,
                observed_at TEXT NOT NULL, event_type TEXT NOT NULL, payload TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS immutable_update BEFORE UPDATE ON events
            BEGIN SELECT RAISE(ABORT, 'append-only'); END;
            CREATE TRIGGER IF NOT EXISTS immutable_delete BEFORE DELETE ON events
            BEGIN SELECT RAISE(ABORT, 'append-only'); END;
        """)

    def get(self, key: str) -> dict | None:
        row = self.connection.execute(
            "SELECT payload FROM events WHERE event_key=?", (key,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def append(self, key: str, event_type: str, payload: dict) -> bool:
        body = json.dumps({**payload, **LABELS}, sort_keys=True, allow_nan=False)
        with self.connection:
            cursor = self.connection.execute(
                "INSERT OR IGNORE INTO events(event_key,observed_at,event_type,payload) "
                "VALUES(?,?,?,?)",
                (key, datetime.now(UTC).isoformat(), event_type, body),
            )
        return cursor.rowcount == 1
