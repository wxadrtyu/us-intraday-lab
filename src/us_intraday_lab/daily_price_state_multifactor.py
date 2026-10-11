"""Frozen sparse daily price-state multi-factor diagnostic."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from us_intraday_lab.daily_technical_multifactor import (
    DECISION_BARS,
    DELAY_EXITS,
    HOLDING_BARS,
    STANDARD_EXITS,
    TOP_COUNTS,
    _daily_source_files,
    _load_daily_bars,
    _load_event_cube,
    _metrics,
    _tree_sha256,
    _validate_daily_bars,
    daily_returns,
    map_features_to_sessions,
)

FAMILIES = (
    "capitulation_recovery",
    "downside_exhaustion",
    "compression_uptrend",
    "volume_accumulation",
    "failed_breakdown_recovery",
)

ORIENTATIONS = {
    "capitulation_recovery": (
        ("return_1", -1.0),
        ("volume_ratio_20", 1.0),
        ("close_location", 1.0),
    ),
    "downside_exhaustion": (
        ("return_5", -1.0),
        ("range_ratio_20", 1.0),
        ("close_location", -1.0),
    ),
    "compression_uptrend": (
        ("compression_5_20", -1.0),
        ("momentum_20", 1.0),
        ("close_location", 1.0),
    ),
    "volume_accumulation": (
        ("return_1", 1.0),
        ("volume_ratio_20", 1.0),
        ("close_location", 1.0),
        ("body_location", 1.0),
    ),
    "failed_breakdown_recovery": (
        ("return_5", -1.0),
        ("range_ratio_20", 1.0),
        ("close_location", 1.0),
        ("body_location", 1.0),
    ),
}


@dataclass(frozen=True, slots=True)
class Specification:
    family: str
    decision_bar: int
    holding_bars: int
    top_count: int


def specifications() -> tuple[Specification, ...]:
    result = tuple(
        Specification(family, decision, holding, top_count)
        for family in FAMILIES
        for decision in DECISION_BARS
        for holding in HOLDING_BARS
        for top_count in TOP_COUNTS
    )
    if len(result) != 400 or len(set(result)) != 400:
        raise AssertionError("DAILY_PRICE_STATE_GRID_INVALID")
    return result


def build_price_state_features(daily_bars: pd.DataFrame) -> pd.DataFrame:
    frame = _validate_daily_bars(daily_bars)
    grouped = frame.groupby("symbol", sort=False, observed=True)
    prior_close = grouped["close"].shift(1)
    frame["return_1"] = frame["close"] / prior_close - 1.0
    frame["return_5"] = frame["close"] / grouped["close"].shift(5) - 1.0
    frame["momentum_20"] = frame["close"] / grouped["close"].shift(20) - 1.0
    daily_range = frame["high"] - frame["low"]
    positive_range = daily_range.gt(0)
    frame["close_location"] = ((frame["close"] - frame["low"]) / daily_range).where(
        positive_range
    )
    frame["body_location"] = ((frame["close"] - frame["open"]) / daily_range).where(
        positive_range
    )
    true_range = pd.concat(
        [
            daily_range,
            (frame["high"] - prior_close).abs(),
            (frame["low"] - prior_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    median_range_5 = true_range.groupby(
        frame["symbol"], sort=False, observed=True
    ).transform(lambda values: values.rolling(5, min_periods=5).median())
    median_range_20 = true_range.groupby(
        frame["symbol"], sort=False, observed=True
    ).transform(lambda values: values.rolling(20, min_periods=20).median())
    frame["range_ratio_20"] = (true_range / median_range_20).where(
        median_range_20.gt(0)
    )
    frame["compression_5_20"] = (median_range_5 / median_range_20).where(
        median_range_20.gt(0)
    )
    median_volume_20 = grouped["volume"].transform(
        lambda values: values.rolling(20, min_periods=20).median()
    )
    frame["volume_ratio_20"] = (frame["volume"] / median_volume_20).where(
        median_volume_20.gt(0)
    )
    prior_low_20 = grouped["low"].transform(
        lambda values: values.shift(1).rolling(20, min_periods=20).min()
    )
    frame["failed_breakdown"] = frame["low"].lt(prior_low_20) & frame["close"].gt(
        prior_low_20
    )
    frame = frame.rename(columns={"session_date": "feature_date"})
    columns = [
        "return_1",
        "return_5",
        "momentum_20",
        "close_location",
        "body_location",
        "range_ratio_20",
        "compression_5_20",
        "volume_ratio_20",
        "failed_breakdown",
    ]
    return frame.loc[:, ["symbol", "feature_date", *columns]]


def _eligibility(frame: pd.DataFrame, family: str) -> pd.Series:
    q20_return_1 = frame["return_1"].groupby(
        frame["session_date"], observed=True
    ).transform(lambda values: values.quantile(0.20))
    q20_return_5 = frame["return_5"].groupby(
        frame["session_date"], observed=True
    ).transform(lambda values: values.quantile(0.20))
    if family == "capitulation_recovery":
        return (
            frame["return_1"].le(q20_return_1)
            & frame["volume_ratio_20"].ge(1.25)
            & frame["close_location"].ge(0.55)
        )
    if family == "downside_exhaustion":
        return (
            frame["return_5"].le(q20_return_5)
            & frame["range_ratio_20"].ge(1.25)
            & frame["close_location"].le(0.35)
        )
    if family == "compression_uptrend":
        return (
            frame["compression_5_20"].le(0.70)
            & frame["momentum_20"].gt(0)
            & frame["close_location"].ge(0.60)
        )
    if family == "volume_accumulation":
        return (
            frame["return_1"].gt(0)
            & frame["volume_ratio_20"].ge(1.50)
            & frame["close_location"].ge(0.70)
            & frame["body_location"].gt(0)
        )
    if family == "failed_breakdown_recovery":
        return (
            frame["failed_breakdown"].eq(True)
            & frame["body_location"].gt(0)
            & frame["close_location"].ge(0.60)
        )
    raise ValueError(f"DAILY_PRICE_STATE_UNKNOWN_FAMILY:{family}")


def score_family(frame: pd.DataFrame, family: str) -> pd.Series:
    if family not in ORIENTATIONS:
        raise ValueError(f"DAILY_PRICE_STATE_UNKNOWN_FAMILY:{family}")
    ranks = []
    for column, direction in ORIENTATIONS[family]:
        oriented = frame[column] * direction
        ranks.append(
            oriented.groupby(frame["session_date"], observed=True).rank(
                method="average", pct=True
            )
        )
    score = pd.concat(ranks, axis=1).mean(axis=1, skipna=False)
    return score.where(_eligibility(frame, family))


def evaluate_grid(feature_scores: pd.DataFrame, event_cube: pd.DataFrame) -> pd.DataFrame:
    score_required = {"symbol", "session_date", *FAMILIES}
    price_columns = {"p1_open", "p2_open", "p3_open", "p5_open", "p7_open", "p8_open"}
    cube_required = {"symbol", "session_date", "bar_idx", *price_columns}
    if not score_required.issubset(feature_scores.columns) or not cube_required.issubset(
        event_cube.columns
    ):
        raise ValueError("DAILY_PRICE_STATE_GRID_SCHEMA_INVALID")
    scores = feature_scores.loc[:, sorted(score_required)].copy()
    cube = event_cube.loc[:, sorted(cube_required)].copy()
    scores["session_date"] = pd.to_datetime(scores["session_date"]).astype(
        "datetime64[ns]"
    )
    cube["session_date"] = pd.to_datetime(cube["session_date"]).astype("datetime64[ns]")
    if scores[["symbol", "session_date"]].duplicated().any():
        raise ValueError("DAILY_PRICE_STATE_SCORE_KEY_DUPLICATE")
    if cube[["symbol", "session_date", "bar_idx"]].duplicated().any():
        raise ValueError("DAILY_PRICE_STATE_EVENT_KEY_DUPLICATE")
    active = cube.merge(scores, on=["symbol", "session_date"], how="inner", validate="many_to_one")
    calendar = pd.DatetimeIndex(sorted(cube["session_date"].unique()))
    records: list[dict[str, object]] = []
    for spec in specifications():
        subset = active.loc[
            active["bar_idx"].eq(spec.decision_bar) & active[spec.family].notna()
        ].sort_values(
            ["session_date", spec.family, "symbol"],
            ascending=[True, False, True],
            kind="stable",
        )
        selection_rank = subset.groupby("session_date", observed=True).cumcount() + 1
        selected = subset.loc[selection_rank.le(spec.top_count)]
        standard, signal_sessions, standard_valid = daily_returns(
            selected,
            entry="p1_open",
            exit_column=STANDARD_EXITS[spec.holding_bars],
            cost=0.0009,
            calendar=calendar,
        )
        stress, _, stress_valid = daily_returns(
            selected,
            entry="p1_open",
            exit_column=STANDARD_EXITS[spec.holding_bars],
            cost=0.0018,
            calendar=calendar,
        )
        delayed, _, delay_valid = daily_returns(
            selected,
            entry="p2_open",
            exit_column=DELAY_EXITS[spec.holding_bars],
            cost=0.0009,
            calendar=calendar,
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
                "delay_1bar_9bp": delay_metrics,
                "retention_floor_passed": retained,
            }
        )
    cells = pd.DataFrame.from_records(records)
    if len(cells) != 400:
        raise RuntimeError("DAILY_PRICE_STATE_GRID_EXECUTION_INCOMPLETE")
    return cells


def training_decision(cells: pd.DataFrame) -> str:
    retained = cells.loc[cells["retention_floor_passed"].eq(True)]
    if int(cells["valid"].eq(False).sum()) == 0 and retained["family"].nunique() >= 2:
        return "ACQUIRE_DEVELOPMENT_DAILY_PRICE_STATE_DATA"
    return "ABANDON_DAILY_PRICE_STATE_NO_VERSION_CREATED"


def run_diagnostic(
    *,
    daily_root: Path,
    event_cube_path: Path,
    expected_daily_sha256: str,
    expected_event_sha256: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    started = time.perf_counter()
    source_files = _daily_source_files(daily_root)
    if _tree_sha256(source_files) != expected_daily_sha256:
        raise RuntimeError("DAILY_PRICE_STATE_DAILY_SOURCE_HASH_MISMATCH")
    cube, excluded_outside_training = _load_event_cube(
        event_cube_path, expected_event_sha256
    )
    daily_bars = _load_daily_bars(
        source_files, cube.loc[:, ["symbol"]].drop_duplicates()
    )
    primitives = build_price_state_features(daily_bars)
    sessions = cube.loc[:, ["symbol", "session_date"]].drop_duplicates()
    mapped = map_features_to_sessions(primitives, sessions)
    for family in FAMILIES:
        mapped[family] = score_family(mapped, family)
    cells = evaluate_grid(mapped.loc[:, ["symbol", "session_date", *FAMILIES]], cube)
    retained = cells.loc[cells["retention_floor_passed"].eq(True)]
    eligibility = {
        family: {
            "pairs": int(mapped[family].notna().sum()),
            "symbols": int(mapped.loc[mapped[family].notna(), "symbol"].nunique()),
            "sessions": int(
                mapped.loc[mapped[family].notna(), "session_date"].nunique()
            ),
        }
        for family in FAMILIES
    }
    summary: dict[str, object] = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "diagnostic_id": "daily-price-state-multifactor-training-v1",
        "period": "2021-01-01/2023-12-31",
        "sample_scope": "527-symbol coverage-limited sample; not full market",
        "daily_source_sha256": expected_daily_sha256,
        "daily_source_files": len(source_files),
        "daily_source_bytes": sum(path.stat().st_size for path in source_files),
        "event_cube_sha256": expected_event_sha256,
        "event_rows": len(cube),
        "container_rows_excluded_outside_training": excluded_outside_training,
        "calendar_sessions": int(mapped["session_date"].nunique()),
        "family_eligibility": eligibility,
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
