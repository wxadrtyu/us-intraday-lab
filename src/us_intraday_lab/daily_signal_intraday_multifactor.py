"""Frozen daily-signal, same-session technical multi-factor diagnostic."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from us_intraday_lab.daily_risk_budget_multifactor import (
    FAMILIES,
    build_risk_budget_features,
    score_family,
)
from us_intraday_lab.daily_technical_multifactor import (
    TRAIN_END,
    TRAIN_START,
    _daily_source_files,
    _load_daily_bars,
    _load_event_cube,
    _metrics,
    _tree_sha256,
)

SIGNAL_LAGS = (1, 2, 3, 5)
TOP_COUNTS = (5, 10, 20, 40, 80)
GAP_MODES = ("all", "pullback", "quiet", "followthrough")


@dataclass(frozen=True, slots=True)
class Specification:
    family: str
    signal_lag: int
    top_count: int
    gap_mode: str


def specifications() -> tuple[Specification, ...]:
    result = tuple(
        Specification(family, lag, top_count, gap_mode)
        for family in FAMILIES
        for lag in SIGNAL_LAGS
        for top_count in TOP_COUNTS
        for gap_mode in GAP_MODES
    )
    if len(result) != 400 or len(set(result)) != 400:
        raise AssertionError("DAILY_SIGNAL_INTRADAY_GRID_INVALID")
    return result


def _prepare_scores(scores: pd.DataFrame) -> dict[pd.Timestamp, pd.DataFrame]:
    required = {"symbol", "session_date", "score"}
    if not required.issubset(scores.columns):
        raise ValueError("DAILY_SIGNAL_INTRADAY_SCORE_SCHEMA_INVALID")
    frame = scores.loc[:, ["symbol", "session_date", "score"]].copy()
    frame["session_date"] = pd.to_datetime(frame["session_date"]).astype(
        "datetime64[ns]"
    )
    if frame[["symbol", "session_date"]].duplicated().any():
        raise ValueError("DAILY_SIGNAL_INTRADAY_SCORE_KEY_DUPLICATE")
    return {
        session: group.loc[group["score"].notna(), ["symbol", "score"]]
        for session, group in frame.groupby("session_date", observed=True)
    }


def _prepare_trades(trades: pd.DataFrame) -> tuple[pd.DatetimeIndex, dict[pd.Timestamp, pd.DataFrame]]:
    required = {"symbol", "session_date", "open", "close", "prior_close"}
    if not required.issubset(trades.columns):
        raise ValueError("DAILY_SIGNAL_INTRADAY_TRADE_SCHEMA_INVALID")
    frame = trades.loc[:, list(required)].copy()
    frame["session_date"] = pd.to_datetime(frame["session_date"]).astype(
        "datetime64[ns]"
    )
    if frame[["symbol", "session_date"]].duplicated().any():
        raise ValueError("DAILY_SIGNAL_INTRADAY_TRADE_KEY_DUPLICATE")
    for column in ("open", "close", "prior_close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if not np.isfinite(frame["open"]).all() or not frame["open"].gt(0).all():
        raise ValueError("DAILY_SIGNAL_INTRADAY_OPEN_INVALID")
    calendar = pd.DatetimeIndex(sorted(frame["session_date"].unique()))
    return calendar, {
        session: group.loc[:, ["symbol", "open", "close", "prior_close"]]
        for session, group in frame.groupby("session_date", observed=True)
    }


def _gap_filter(frame: pd.DataFrame, mode: str) -> pd.Series:
    if mode == "all":
        return pd.Series(True, index=frame.index)
    if mode == "pullback":
        return frame["gap"].le(0.0)
    if mode == "quiet":
        return frame["gap"].abs().le(0.015)
    if mode == "followthrough":
        return frame["gap"].gt(0.0)
    raise ValueError(f"DAILY_SIGNAL_INTRADAY_UNKNOWN_GAP_MODE:{mode}")


def _intraday_returns_prepared(
    score_by_date: dict[pd.Timestamp, pd.DataFrame],
    calendar: pd.DatetimeIndex,
    trade_by_date: dict[pd.Timestamp, pd.DataFrame],
    *,
    top_count: int,
    signal_lag: int,
    gap_mode: str,
    cost_rate: float,
    evaluation_start: date | None,
    evaluation_end: date | None,
) -> tuple[pd.Series, int, bool]:
    values: list[float] = []
    dates: list[pd.Timestamp] = []
    signal_sessions = 0
    for index, current_date in enumerate(calendar):
        if index < signal_lag:
            continue
        if evaluation_start is not None and current_date.date() < evaluation_start:
            continue
        if evaluation_end is not None and current_date.date() > evaluation_end:
            continue
        candidates = score_by_date.get(calendar[index - signal_lag], pd.DataFrame())
        current = trade_by_date[current_date]
        if candidates.empty:
            values.append(0.0)
            dates.append(current_date)
            continue
        merged = candidates.merge(current, on="symbol", how="inner", validate="one_to_one")
        merged = merged.loc[
            np.isfinite(merged["prior_close"]) & merged["prior_close"].gt(0)
        ].copy()
        merged["gap"] = merged["open"] / merged["prior_close"] - 1.0
        selected = merged.loc[_gap_filter(merged, gap_mode)].sort_values(
            ["score", "symbol"], ascending=[False, True], kind="stable"
        ).head(top_count)
        if selected.empty:
            values.append(0.0)
            dates.append(current_date)
            continue
        if not np.isfinite(selected["close"]).all() or not selected["close"].gt(0).all():
            return pd.Series(dtype=float), signal_sessions, False
        gross = (selected["close"] / selected["open"] - 1.0).mean()
        values.append(float(gross - cost_rate))
        dates.append(current_date)
        signal_sessions += 1
    return pd.Series(values, index=pd.DatetimeIndex(dates), dtype=float), signal_sessions, True


def intraday_returns(
    scores: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    top_count: int,
    signal_lag: int,
    gap_mode: str,
    cost_rate: float,
    evaluation_start: date | None = None,
    evaluation_end: date | None = None,
) -> tuple[pd.Series, int, bool]:
    calendar, trade_by_date = _prepare_trades(trades)
    return _intraday_returns_prepared(
        _prepare_scores(scores),
        calendar,
        trade_by_date,
        top_count=top_count,
        signal_lag=signal_lag,
        gap_mode=gap_mode,
        cost_rate=cost_rate,
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
    )


def evaluate_grid(
    feature_scores: pd.DataFrame,
    trades: pd.DataFrame,
    *,
    evaluation_start: date = TRAIN_START,
    evaluation_end: date = TRAIN_END,
) -> pd.DataFrame:
    required = {"symbol", "feature_date", *FAMILIES}
    if not required.issubset(feature_scores.columns):
        raise ValueError("DAILY_SIGNAL_INTRADAY_GRID_SCHEMA_INVALID")
    calendar, trade_by_date = _prepare_trades(trades)
    prepared = {
        family: _prepare_scores(
            feature_scores.loc[:, ["symbol", "feature_date", family]].rename(
                columns={"feature_date": "session_date", family: "score"}
            )
        )
        for family in FAMILIES
    }
    cache: dict[tuple[str, int, int, str, float], tuple[pd.Series, int, bool]] = {}

    def calculate(
        family: str, lag: int, top_count: int, gap_mode: str, cost: float
    ) -> tuple[pd.Series, int, bool]:
        key = (family, lag, top_count, gap_mode, cost)
        if key not in cache:
            cache[key] = _intraday_returns_prepared(
                prepared[family],
                calendar,
                trade_by_date,
                top_count=top_count,
                signal_lag=lag,
                gap_mode=gap_mode,
                cost_rate=cost,
                evaluation_start=evaluation_start,
                evaluation_end=evaluation_end,
            )
        return cache[key]

    records: list[dict[str, object]] = []
    for spec in specifications():
        standard, sessions, standard_valid = calculate(
            spec.family, spec.signal_lag, spec.top_count, spec.gap_mode, 0.0009
        )
        stress, _, stress_valid = calculate(
            spec.family, spec.signal_lag, spec.top_count, spec.gap_mode, 0.0018
        )
        delayed, _, delay_valid = calculate(
            spec.family, spec.signal_lag + 1, spec.top_count, spec.gap_mode, 0.0009
        )
        valid = standard_valid and stress_valid and delay_valid
        standard_metrics = _metrics(standard)
        stress_metrics = _metrics(stress)
        delay_metrics = _metrics(delayed)
        retained = bool(
            valid
            and sessions >= 500
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
                "signal_sessions": sessions,
                "valid": valid,
                "standard_9bp": standard_metrics,
                "cost_18bp": stress_metrics,
                "delay_1session_9bp": delay_metrics,
                "retention_floor_passed": retained,
            }
        )
    cells = pd.DataFrame.from_records(records)
    if len(cells) != 400:
        raise RuntimeError("DAILY_SIGNAL_INTRADAY_GRID_EXECUTION_INCOMPLETE")
    return cells


def training_decision(cells: pd.DataFrame) -> str:
    retained = cells.loc[cells["retention_floor_passed"].eq(True)]
    if int(cells["valid"].eq(False).sum()) == 0 and retained["family"].nunique() >= 2:
        return "ACQUIRE_DEVELOPMENT_DAILY_SIGNAL_INTRADAY_DATA"
    return "ABANDON_DAILY_SIGNAL_INTRADAY_NO_VERSION_CREATED"


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
        raise RuntimeError("DAILY_SIGNAL_INTRADAY_SOURCE_HASH_MISMATCH")
    container, excluded = _load_event_cube(
        symbol_container_path, expected_symbol_container_sha256
    )
    daily_bars = _load_daily_bars(
        source_files, container.loc[:, ["symbol"]].drop_duplicates()
    )
    features = build_risk_budget_features(daily_bars)
    for family in FAMILIES:
        features[family] = score_family(features, family)
    trades = daily_bars.loc[:, ["symbol", "session_date", "open", "close"]].copy()
    trades["prior_close"] = trades.groupby("symbol", sort=False, observed=True)[
        "close"
    ].shift(1)
    cells = evaluate_grid(features, trades)
    retained = cells.loc[cells["retention_floor_passed"].eq(True)]
    return cells, {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "diagnostic_id": "daily-signal-intraday-multifactor-training-v1",
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
