"""Frozen training-only daily technical risk-budget multi-factor diagnostic."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from us_intraday_lab.daily_swing_multifactor import (
    _target_weights,
    _turnover,
    build_swing_features,
)
from us_intraday_lab.daily_technical_multifactor import (
    TRAIN_END,
    TRAIN_START,
    _daily_source_files,
    _load_daily_bars,
    _load_event_cube,
    _metrics,
    _tree_sha256,
    _validate_daily_bars,
)

FAMILIES = (
    "diversified_quality",
    "defensive_momentum",
    "liquid_breakout",
    "stable_reversal",
    "trend_reversal_blend",
)
SIGNAL_LAGS = (1, 2, 3, 5)
HOLDING_SESSIONS = (1, 2, 5, 10)
TOP_COUNTS = (10, 20, 40, 80, 120)

ORIENTATIONS = {
    "diversified_quality": (
        ("momentum_20_5", 1.0),
        ("momentum_60_5", 1.0),
        ("trend_efficiency_20", 1.0),
        ("breakout_20", 1.0),
        ("downside_volatility_20", -1.0),
    ),
    "defensive_momentum": (
        ("momentum_60_5", 1.0),
        ("residual_momentum_60_5", 1.0),
        ("realized_volatility_20", -1.0),
        ("downside_volatility_20", -1.0),
        ("drawdown_60", 1.0),
    ),
    "liquid_breakout": (
        ("breakout_20", 1.0),
        ("momentum_20_5", 1.0),
        ("volume_ratio_5_20", 1.0),
        ("trend_efficiency_20", 1.0),
        ("dollar_volume_rank", 1.0),
    ),
    "stable_reversal": (
        ("return_1", -1.0),
        ("return_5", -1.0),
        ("realized_volatility_20", -1.0),
        ("downside_volatility_20", -1.0),
        ("drawdown_60", 1.0),
    ),
    "trend_reversal_blend": (
        ("momentum_60_5", 1.0),
        ("trend_efficiency_20", 1.0),
        ("return_1", -1.0),
        ("realized_volatility_20", -1.0),
        ("drawdown_60", 1.0),
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
        raise AssertionError("DAILY_RISK_BUDGET_GRID_INVALID")
    return result


def build_risk_budget_features(daily_bars: pd.DataFrame) -> pd.DataFrame:
    bars = _validate_daily_bars(daily_bars)
    features = build_swing_features(bars)
    bars["dollar_volume"] = bars["close"] * bars["volume"]
    bars["dollar_volume_median_20"] = bars.groupby(
        "symbol", sort=False, observed=True
    )["dollar_volume"].transform(
        lambda values: values.rolling(20, min_periods=20).median()
    )
    liquidity = bars.rename(columns={"session_date": "feature_date"}).loc[
        :,
        ["symbol", "feature_date", "close", "dollar_volume_median_20"],
    ]
    result = features.merge(
        liquidity, on=["symbol", "feature_date"], how="inner", validate="one_to_one"
    )
    result["eligible"] = result["close"].ge(5.0) & result[
        "dollar_volume_median_20"
    ].ge(5_000_000.0)
    result["dollar_volume_rank"] = result["dollar_volume_median_20"].groupby(
        result["feature_date"], observed=True
    ).rank(method="average", pct=True)
    return result


def score_family(frame: pd.DataFrame, family: str) -> pd.Series:
    if family not in ORIENTATIONS:
        raise ValueError(f"DAILY_RISK_BUDGET_UNKNOWN_FAMILY:{family}")
    ranks = [
        (frame[column] * direction)
        .groupby(frame["feature_date"], observed=True)
        .rank(method="average", pct=True)
        for column, direction in ORIENTATIONS[family]
    ]
    score = pd.concat(ranks, axis=1).mean(axis=1, skipna=False)
    return score.where(frame["eligible"].eq(True))


def market_exposure(daily_bars: pd.DataFrame) -> pd.Series:
    bars = _validate_daily_bars(daily_bars)
    bars["return_1"] = bars.groupby("symbol", sort=False, observed=True)[
        "close"
    ].pct_change(fill_method=None)
    market_return = bars.groupby("session_date", observed=True)["return_1"].mean()
    market_volatility = market_return.rolling(20, min_periods=20).std(ddof=1) * np.sqrt(
        252.0
    )
    exposure = (0.15 / market_volatility).clip(lower=0.25, upper=1.0).shift(1)
    exposure.index = pd.DatetimeIndex(exposure.index)
    return exposure


def capped_inverse_volatility_weights(
    volatility: pd.Series, *, cap: float = 0.10
) -> dict[str, float]:
    numeric = pd.to_numeric(volatility, errors="coerce")
    valid = numeric.loc[np.isfinite(numeric) & numeric.gt(0)]
    if valid.empty:
        return {}
    raw = (1.0 / valid) / (1.0 / valid).sum()
    return {str(symbol): float(min(weight, cap)) for symbol, weight in raw.items()}


@dataclass(frozen=True, slots=True)
class _PreparedMarket:
    calendar: pd.DatetimeIndex
    open_by_date: dict[pd.Timestamp, pd.Series]


def _prepare_market(opens: pd.DataFrame) -> _PreparedMarket:
    required = {"symbol", "session_date", "open"}
    if not required.issubset(opens.columns):
        raise ValueError("DAILY_RISK_BUDGET_PORTFOLIO_SCHEMA_INVALID")
    frame = opens.loc[:, ["symbol", "session_date", "open"]].copy()
    frame["session_date"] = pd.to_datetime(frame["session_date"]).astype(
        "datetime64[ns]"
    )
    if frame[["symbol", "session_date"]].duplicated().any():
        raise ValueError("DAILY_RISK_BUDGET_PORTFOLIO_KEY_DUPLICATE")
    frame["open"] = pd.to_numeric(frame["open"], errors="coerce")
    if not np.isfinite(frame["open"]).all() or not frame["open"].gt(0).all():
        raise ValueError("DAILY_RISK_BUDGET_OPEN_INVALID")
    return _PreparedMarket(
        calendar=pd.DatetimeIndex(sorted(frame["session_date"].unique())),
        open_by_date={
            session: group.set_index("symbol")["open"]
            for session, group in frame.groupby("session_date", observed=True)
        },
    )


def _prepare_scores(scores: pd.DataFrame) -> dict[pd.Timestamp, pd.DataFrame]:
    required = {
        "symbol",
        "session_date",
        "score",
        "realized_volatility_20",
        "eligible",
    }
    if not required.issubset(scores.columns):
        raise ValueError("DAILY_RISK_BUDGET_PORTFOLIO_SCHEMA_INVALID")
    frame = scores.loc[:, list(required)].copy()
    frame["session_date"] = pd.to_datetime(frame["session_date"]).astype(
        "datetime64[ns]"
    )
    if frame[["symbol", "session_date"]].duplicated().any():
        raise ValueError("DAILY_RISK_BUDGET_PORTFOLIO_KEY_DUPLICATE")
    return {
        session: group.loc[
            group["score"].notna() & group["eligible"].eq(True),
            ["symbol", "score", "realized_volatility_20"],
        ]
        for session, group in frame.groupby("session_date", observed=True)
    }


def _cohort_sequence(
    market: _PreparedMarket,
    score_by_date: dict[pd.Timestamp, pd.DataFrame],
    exposure: pd.Series,
    *,
    top_count: int,
    signal_lag: int,
) -> tuple[list[dict[str, float]], int]:
    cohorts: list[dict[str, float]] = []
    signal_sessions = 0
    for index in range(len(market.calendar) - 1):
        current_date = market.calendar[index]
        if index < signal_lag or current_date not in exposure.index:
            cohorts.append({})
            continue
        signal_date = market.calendar[index - signal_lag]
        candidates = score_by_date.get(signal_date, pd.DataFrame())
        if not candidates.empty:
            candidates = candidates.loc[
                candidates["symbol"].isin(market.open_by_date[current_date].index)
            ].sort_values(["score", "symbol"], ascending=[False, True], kind="stable")
        selected = candidates.head(top_count)
        risk = float(exposure.loc[current_date])
        if selected.empty or not np.isfinite(risk):
            cohort: dict[str, float] = {}
        else:
            base = capped_inverse_volatility_weights(
                selected.set_index("symbol")["realized_volatility_20"]
            )
            cohort = {symbol: weight * risk for symbol, weight in base.items()}
        cohorts.append(cohort)
        signal_sessions += bool(cohort)
    return cohorts, signal_sessions


def _returns_from_cohorts(
    market: _PreparedMarket,
    cohort_sequence: list[dict[str, float]],
    *,
    holding_sessions: int,
    cost_rate: float,
    evaluation_start: date | None,
    evaluation_end: date | None,
) -> tuple[pd.Series, bool]:
    active: deque[dict[str, float]] = deque(maxlen=holding_sessions)
    previous: dict[str, float] = {}
    values: list[float] = []
    dates: list[pd.Timestamp] = []
    for index, cohort in enumerate(cohort_sequence):
        current_date = market.calendar[index]
        next_date = market.calendar[index + 1]
        active.append(cohort)
        target = _target_weights(active, holding_sessions)
        current_opens = market.open_by_date[current_date]
        next_opens = market.open_by_date[next_date]
        if any(
            symbol not in current_opens.index or symbol not in next_opens.index
            for symbol in target
        ):
            return pd.Series(dtype=float), False
        gross = sum(
            weight * (float(next_opens[symbol]) / float(current_opens[symbol]) - 1.0)
            for symbol, weight in target.items()
        )
        net = gross - cost_rate * _turnover(previous, target)
        if (
            (evaluation_start is None or current_date.date() >= evaluation_start)
            and (evaluation_end is None or current_date.date() <= evaluation_end)
        ):
            values.append(net)
            dates.append(current_date)
        previous = target
    return pd.Series(values, index=pd.DatetimeIndex(dates), dtype=float), True


def portfolio_returns(
    scores: pd.DataFrame,
    opens: pd.DataFrame,
    exposure: pd.Series,
    *,
    top_count: int,
    holding_sessions: int,
    signal_lag: int,
    cost_rate: float,
    evaluation_start: date | None = None,
    evaluation_end: date | None = None,
) -> tuple[pd.Series, int, bool]:
    market = _prepare_market(opens)
    sequence, sessions = _cohort_sequence(
        market,
        _prepare_scores(scores),
        exposure,
        top_count=top_count,
        signal_lag=signal_lag,
    )
    returns, valid = _returns_from_cohorts(
        market,
        sequence,
        holding_sessions=holding_sessions,
        cost_rate=cost_rate,
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
    )
    return returns, sessions, valid


def evaluate_grid(
    feature_scores: pd.DataFrame,
    opens: pd.DataFrame,
    exposure: pd.Series,
    *,
    evaluation_start: date = TRAIN_START,
    evaluation_end: date = TRAIN_END,
) -> pd.DataFrame:
    required = {
        "symbol",
        "feature_date",
        "realized_volatility_20",
        "eligible",
        *FAMILIES,
    }
    if not required.issubset(feature_scores.columns):
        raise ValueError("DAILY_RISK_BUDGET_SCORE_SCHEMA_INVALID")
    market = _prepare_market(opens)
    prepared = {
        family: _prepare_scores(
            feature_scores.loc[
                :,
                [
                    "symbol",
                    "feature_date",
                    family,
                    "realized_volatility_20",
                    "eligible",
                ],
            ].rename(columns={"feature_date": "session_date", family: "score"})
        )
        for family in FAMILIES
    }
    lags = sorted(set(SIGNAL_LAGS) | {lag + 1 for lag in SIGNAL_LAGS})
    sequences = {
        (family, lag, top_count): _cohort_sequence(
            market,
            prepared[family],
            exposure,
            top_count=top_count,
            signal_lag=lag,
        )
        for family in FAMILIES
        for lag in lags
        for top_count in TOP_COUNTS
    }
    records: list[dict[str, object]] = []
    for spec in specifications():
        sequence, signal_sessions = sequences[
            (spec.family, spec.signal_lag, spec.top_count)
        ]
        delayed_sequence, _ = sequences[
            (spec.family, spec.signal_lag + 1, spec.top_count)
        ]
        common = {
            "holding_sessions": spec.holding_sessions,
            "evaluation_start": evaluation_start,
            "evaluation_end": evaluation_end,
        }
        standard, standard_valid = _returns_from_cohorts(
            market, sequence, cost_rate=0.0009, **common
        )
        stress, stress_valid = _returns_from_cohorts(
            market, sequence, cost_rate=0.0018, **common
        )
        delayed, delay_valid = _returns_from_cohorts(
            market, delayed_sequence, cost_rate=0.0009, **common
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
        raise RuntimeError("DAILY_RISK_BUDGET_GRID_EXECUTION_INCOMPLETE")
    return cells


def training_decision(cells: pd.DataFrame) -> str:
    retained = cells.loc[cells["retention_floor_passed"].eq(True)]
    if int(cells["valid"].eq(False).sum()) == 0 and retained["family"].nunique() >= 2:
        return "ACQUIRE_DEVELOPMENT_DAILY_RISK_BUDGET_DATA"
    return "ABANDON_DAILY_RISK_BUDGET_NO_VERSION_CREATED"


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
        raise RuntimeError("DAILY_RISK_BUDGET_DAILY_SOURCE_HASH_MISMATCH")
    container, excluded = _load_event_cube(
        symbol_container_path, expected_symbol_container_sha256
    )
    symbols = container.loc[:, ["symbol"]].drop_duplicates()
    daily_bars = _load_daily_bars(source_files, symbols)
    features = build_risk_budget_features(daily_bars)
    for family in FAMILIES:
        features[family] = score_family(features, family)
    cells = evaluate_grid(
        features,
        daily_bars.loc[:, ["symbol", "session_date", "open"]],
        market_exposure(daily_bars),
    )
    retained = cells.loc[cells["retention_floor_passed"].eq(True)]
    return cells, {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "diagnostic_id": "daily-risk-budget-multifactor-training-v1",
        "period": "2021-01-01/2023-12-31",
        "sample_scope": "527-symbol coverage-limited sample; not full market",
        "daily_source_sha256": expected_daily_sha256,
        "daily_source_files": len(source_files),
        "daily_source_bytes": sum(path.stat().st_size for path in source_files),
        "symbol_container_sha256": expected_symbol_container_sha256,
        "container_rows_excluded_outside_training": excluded,
        "daily_rows": len(daily_bars),
        "symbols": int(daily_bars["symbol"].nunique()),
        "cells_completed": len(cells),
        "invalid_cells": int(cells["valid"].eq(False).sum()),
        "retained_cells": len(retained),
        "retained_families": sorted(set(retained["family"])),
        "decision": training_decision(cells),
        "strategy_versions_created": 0,
        "development_or_consumed_loaded": False,
        "news_or_issuer_event_data_loaded": False,
        "paper_activation": False,
        "order_route": "FORBIDDEN",
        "runtime_seconds": time.perf_counter() - started,
    }
