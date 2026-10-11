"""Frozen training-only daily swing technical multi-factor diagnostic."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from us_intraday_lab.daily_technical_multifactor import (
    TRAIN_END,
    TRAIN_START,
    _daily_source_files,
    _load_daily_bars,
    _load_event_cube,
    _metrics,
    _tree_sha256,
    _validate_daily_bars,
    build_daily_features,
)

FAMILIES = (
    "balanced_trend",
    "residual_trend",
    "low_vol_momentum",
    "short_reversal",
    "breakout_volume",
)
SIGNAL_LAGS = (1, 2, 3, 5)
HOLDING_SESSIONS = (1, 2, 5, 10)
TOP_COUNTS = (5, 10, 20, 40, 80)

ORIENTATIONS = {
    "balanced_trend": (
        ("momentum_20_5", 1.0),
        ("momentum_60_5", 1.0),
        ("trend_efficiency_20", 1.0),
        ("downside_volatility_20", -1.0),
    ),
    "residual_trend": (
        ("residual_momentum_60_5", 1.0),
        ("momentum_20_5", 1.0),
        ("trend_efficiency_20", 1.0),
        ("realized_volatility_20", -1.0),
    ),
    "low_vol_momentum": (
        ("momentum_60_5", 1.0),
        ("momentum_20_5", 1.0),
        ("realized_volatility_20", -1.0),
        ("downside_volatility_20", -1.0),
        ("drawdown_60", 1.0),
    ),
    "short_reversal": (
        ("return_1", -1.0),
        ("return_5", -1.0),
        ("realized_volatility_20", -1.0),
        ("drawdown_60", 1.0),
    ),
    "breakout_volume": (
        ("breakout_20", 1.0),
        ("momentum_20_5", 1.0),
        ("volume_ratio_5_20", 1.0),
        ("trend_efficiency_20", 1.0),
    ),
}


@dataclass(frozen=True, slots=True)
class Specification:
    family: str
    signal_lag: int
    holding_sessions: int
    top_count: int


def specifications() -> tuple[Specification, ...]:
    result = tuple(
        Specification(family, lag, holding, top_count)
        for family in FAMILIES
        for lag in SIGNAL_LAGS
        for holding in HOLDING_SESSIONS
        for top_count in TOP_COUNTS
    )
    if len(result) != 400 or len(set(result)) != 400:
        raise AssertionError("DAILY_SWING_GRID_INVALID")
    return result


def build_swing_features(daily_bars: pd.DataFrame) -> pd.DataFrame:
    bars = _validate_daily_bars(daily_bars)
    base = build_daily_features(bars)
    grouped = bars.groupby("symbol", sort=False, observed=True)
    bars["return_1"] = bars["close"] / grouped["close"].shift(1) - 1.0
    bars["return_5"] = bars["close"] / grouped["close"].shift(5) - 1.0
    prior_high_20 = grouped["high"].transform(
        lambda values: values.shift(1).rolling(20, min_periods=20).max()
    )
    bars["breakout_20"] = bars["close"] / prior_high_20 - 1.0
    volume_5 = grouped["volume"].transform(
        lambda values: values.rolling(5, min_periods=5).mean()
    )
    volume_20 = grouped["volume"].transform(
        lambda values: values.rolling(20, min_periods=20).mean()
    )
    bars["volume_ratio_5_20"] = (volume_5 / volume_20).where(volume_20.gt(0))
    extras = bars.rename(columns={"session_date": "feature_date"}).loc[
        :,
        [
            "symbol",
            "feature_date",
            "return_1",
            "return_5",
            "breakout_20",
            "volume_ratio_5_20",
        ],
    ]
    return base.merge(
        extras, on=["symbol", "feature_date"], how="inner", validate="one_to_one"
    )


def score_family(frame: pd.DataFrame, family: str) -> pd.Series:
    if family not in ORIENTATIONS:
        raise ValueError(f"DAILY_SWING_UNKNOWN_FAMILY:{family}")
    ranks = []
    for column, direction in ORIENTATIONS[family]:
        ranks.append(
            (frame[column] * direction)
            .groupby(frame["feature_date"], observed=True)
            .rank(method="average", pct=True)
        )
    return pd.concat(ranks, axis=1).mean(axis=1, skipna=False)


def _target_weights(cohorts: deque[dict[str, float]], holding: int) -> dict[str, float]:
    target: dict[str, float] = {}
    for cohort in cohorts:
        for symbol, weight in cohort.items():
            target[symbol] = target.get(symbol, 0.0) + weight / holding
    return target


def _turnover(previous: dict[str, float], current: dict[str, float]) -> float:
    symbols = set(previous) | set(current)
    stock_change = sum(abs(current.get(s, 0.0) - previous.get(s, 0.0)) for s in symbols)
    previous_cash = 1.0 - sum(previous.values())
    current_cash = 1.0 - sum(current.values())
    return 0.5 * (stock_change + abs(current_cash - previous_cash))


def portfolio_returns(
    scores: pd.DataFrame,
    opens: pd.DataFrame,
    *,
    top_count: int,
    holding_sessions: int,
    signal_lag: int,
    cost_rate: float,
    evaluation_start: date | None = None,
    evaluation_end: date | None = None,
) -> tuple[pd.Series, int, bool]:
    required_scores = {"symbol", "session_date", "score"}
    required_opens = {"symbol", "session_date", "open"}
    if not required_scores.issubset(scores.columns) or not required_opens.issubset(
        opens.columns
    ):
        raise ValueError("DAILY_SWING_PORTFOLIO_SCHEMA_INVALID")
    score_frame = scores.loc[:, ["symbol", "session_date", "score"]].copy()
    open_frame = opens.loc[:, ["symbol", "session_date", "open"]].copy()
    for frame in (score_frame, open_frame):
        frame["session_date"] = pd.to_datetime(frame["session_date"]).astype(
            "datetime64[ns]"
        )
    if score_frame[["symbol", "session_date"]].duplicated().any() or open_frame[
        ["symbol", "session_date"]
    ].duplicated().any():
        raise ValueError("DAILY_SWING_PORTFOLIO_KEY_DUPLICATE")
    open_frame["open"] = pd.to_numeric(open_frame["open"], errors="coerce")
    if not np.isfinite(open_frame["open"]).all() or not open_frame["open"].gt(0).all():
        raise ValueError("DAILY_SWING_OPEN_INVALID")

    calendar = pd.DatetimeIndex(sorted(open_frame["session_date"].unique()))
    score_by_date = {
        session: group.loc[group["score"].notna(), ["symbol", "score"]]
        for session, group in score_frame.groupby("session_date", observed=True)
    }
    open_by_date = {
        session: group.set_index("symbol")["open"]
        for session, group in open_frame.groupby("session_date", observed=True)
    }
    cohorts: deque[dict[str, float]] = deque(maxlen=holding_sessions)
    previous: dict[str, float] = {}
    values: list[float] = []
    value_dates: list[pd.Timestamp] = []
    signal_sessions = 0
    for index in range(len(calendar) - 1):
        current_date = calendar[index]
        next_date = calendar[index + 1]
        if index >= signal_lag:
            signal_date = calendar[index - signal_lag]
            candidates = score_by_date.get(signal_date, pd.DataFrame())
            current_opens = open_by_date[current_date]
            if not candidates.empty:
                candidates = candidates.loc[
                    candidates["symbol"].isin(current_opens.index)
                ].sort_values(
                    ["score", "symbol"], ascending=[False, True], kind="stable"
                )
            selected = candidates.head(top_count)
            cohort = (
                {symbol: 1.0 / len(selected) for symbol in selected["symbol"]}
                if not selected.empty
                else {}
            )
        else:
            cohort = {}
        cohorts.append(cohort)
        if cohort:
            signal_sessions += 1
        target = _target_weights(cohorts, holding_sessions)
        next_opens = open_by_date[next_date]
        if any(symbol not in next_opens.index for symbol in target):
            return pd.Series(dtype=float), signal_sessions, False
        gross = sum(
            weight * (float(next_opens[symbol]) / float(open_by_date[current_date][symbol]) - 1.0)
            for symbol, weight in target.items()
        )
        net = gross - cost_rate * _turnover(previous, target)
        if (
            (evaluation_start is None or current_date.date() >= evaluation_start)
            and (evaluation_end is None or current_date.date() <= evaluation_end)
        ):
            values.append(net)
            value_dates.append(current_date)
        previous = target
    return pd.Series(values, index=pd.DatetimeIndex(value_dates), dtype=float), signal_sessions, True


def evaluate_grid(
    feature_scores: pd.DataFrame,
    opens: pd.DataFrame,
    *,
    evaluation_start: date = TRAIN_START,
    evaluation_end: date = TRAIN_END,
) -> pd.DataFrame:
    required = {"symbol", "feature_date", *FAMILIES}
    if not required.issubset(feature_scores.columns):
        raise ValueError("DAILY_SWING_SCORE_SCHEMA_INVALID")
    records: list[dict[str, object]] = []
    for spec in specifications():
        family_scores = feature_scores.loc[:, ["symbol", "feature_date", spec.family]].rename(
            columns={"feature_date": "session_date", spec.family: "score"}
        )
        kwargs = {
            "top_count": spec.top_count,
            "holding_sessions": spec.holding_sessions,
            "signal_lag": spec.signal_lag,
            "evaluation_start": evaluation_start,
            "evaluation_end": evaluation_end,
        }
        standard, signal_sessions, standard_valid = portfolio_returns(
            family_scores, opens, cost_rate=0.0009, **kwargs
        )
        stress, _, stress_valid = portfolio_returns(
            family_scores, opens, cost_rate=0.0018, **kwargs
        )
        delayed, _, delay_valid = portfolio_returns(
            family_scores,
            opens,
            cost_rate=0.0009,
            **{**kwargs, "signal_lag": spec.signal_lag + 1},
        )
        valid = standard_valid and stress_valid and delay_valid
        standard_metrics = _metrics(standard)
        stress_metrics = _metrics(stress)
        delay_metrics = _metrics(delayed)
        retained = bool(
            valid
            and signal_sessions >= 500
            and standard_metrics["annualized_return"] >= 0.20
            and standard_metrics["information_ratio"] >= 0.80
            and standard_metrics["max_drawdown"] < 0.20
            and standard_metrics["positive_calendar_years"] >= 2
            and stress_metrics["annualized_return"] > 0
            and delay_metrics["annualized_return"] > 0
        )
        records.append(
            {
                **asdict(spec),
                "signal_sessions": signal_sessions,
                "valid": valid,
                "standard_9bp": standard_metrics,
                "cost_18bp": stress_metrics,
                "delay_1session_9bp": delay_metrics,
                "retention_floor_passed": retained,
            }
        )
    cells = pd.DataFrame.from_records(records)
    if len(cells) != 400:
        raise RuntimeError("DAILY_SWING_GRID_EXECUTION_INCOMPLETE")
    return cells


def training_decision(cells: pd.DataFrame) -> str:
    retained = cells.loc[cells["retention_floor_passed"].eq(True)]
    if int(cells["valid"].eq(False).sum()) == 0 and retained["family"].nunique() >= 2:
        return "ACQUIRE_DEVELOPMENT_DAILY_SWING_DATA"
    return "ABANDON_DAILY_SWING_NO_VERSION_CREATED"


def run_diagnostic(
    *,
    daily_root: Path,
    symbol_container_path: Path,
    expected_daily_sha256: str,
    expected_symbol_container_sha256: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    started = time.perf_counter()
    source_files = _daily_source_files(daily_root)
    if _tree_sha256(source_files) != expected_daily_sha256:
        raise RuntimeError("DAILY_SWING_DAILY_SOURCE_HASH_MISMATCH")
    container, excluded_outside_training = _load_event_cube(
        symbol_container_path, expected_symbol_container_sha256
    )
    sample_symbols = container.loc[:, ["symbol"]].drop_duplicates()
    daily_bars = _load_daily_bars(source_files, sample_symbols)
    features = build_swing_features(daily_bars)
    for family in FAMILIES:
        features[family] = score_family(features, family)
    opens = daily_bars.loc[:, ["symbol", "session_date", "open"]]
    cells = evaluate_grid(features, opens)
    retained = cells.loc[cells["retention_floor_passed"].eq(True)]
    summary: dict[str, object] = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "diagnostic_id": "daily-swing-multifactor-training-v1",
        "period": "2021-01-01/2023-12-31",
        "sample_scope": "527-symbol coverage-limited sample; not full market",
        "daily_source_sha256": expected_daily_sha256,
        "daily_source_files": len(source_files),
        "daily_source_bytes": sum(path.stat().st_size for path in source_files),
        "symbol_container_sha256": expected_symbol_container_sha256,
        "container_rows_excluded_outside_training": excluded_outside_training,
        "daily_rows": len(daily_bars),
        "symbols": int(daily_bars["symbol"].nunique()),
        "cells_completed": len(cells),
        "invalid_cells": int(cells["valid"].eq(False).sum()),
        "retained_cells": len(retained),
        "retained_families": sorted(set(retained["family"])),
        "decision": training_decision(cells),
        "strategy_versions_created": 0,
        "development_or_consumed_loaded": False,
        "paper_activation": False,
        "order_route": "FORBIDDEN",
        "runtime_seconds": time.perf_counter() - started,
    }
    return cells, summary
