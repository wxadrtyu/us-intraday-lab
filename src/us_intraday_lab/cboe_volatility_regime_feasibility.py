"""Frozen training-only Cboe volatility-regime feasibility diagnostic."""

from __future__ import annotations

import hashlib
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from us_intraday_lab.news_training_feasibility import (
    DELAY_EXITS,
    STANDARD_EXITS,
    _daily_returns,
    _metrics,
)

FAMILIES = (
    "near_term_fear_inversion_reversal",
    "vol_of_vol_stress_reversal",
    "oil_volatility_shock_continuation",
    "gold_volatility_divergence_reversal",
    "em_volatility_divergence_reversal",
)
DECISION_BARS = (2, 5, 11, 17, 23)
HOLDING_BARS = (1, 2, 4, 6)
TOP_COUNTS = (1, 3, 5, 10)
TRAIN_START = date(2021, 1, 1)
TRAIN_END = date(2023, 12, 31)
FAMILY_FEATURES = {
    "near_term_fear_inversion_reversal": ("vix9d_vix_z20", "reversal"),
    "vol_of_vol_stress_reversal": ("vvix_z20", "reversal"),
    "oil_volatility_shock_continuation": ("ovx_vix_change_1", "continuation"),
    "gold_volatility_divergence_reversal": ("gvz_vix_change_1", "reversal"),
    "em_volatility_divergence_reversal": ("vxeem_vix_change_1", "reversal"),
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
        raise AssertionError("CBOE_DIAGNOSTIC_GRID_INVALID")
    return result


def _percentile(frame: pd.DataFrame, values: pd.Series) -> pd.Series:
    ranked = frame.loc[:, ["session_date", "bar_idx"]].copy()
    ranked["value"] = pd.to_numeric(values, errors="coerce")
    return ranked.groupby(["session_date", "bar_idx"], observed=True)["value"].rank(
        method="average", pct=True
    )


def score_family(
    frame: pd.DataFrame,
    family: str,
    family_features: dict[str, tuple[str, str]] = FAMILY_FEATURES,
) -> pd.Series:
    """Score one exogenous stress regime without emitting quiet-regime signals."""
    if family not in family_features:
        raise ValueError(f"CBOE_DIAGNOSTIC_FAMILY_INVALID:{family}")
    feature, direction = family_features[family]
    active = pd.to_numeric(frame[feature], errors="coerce").where(lambda value: value > 0)
    current = _percentile(frame, frame["session_return"])
    base = current if direction == "continuation" else 1.0 - current
    return active * base


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_and_merge(
    events_path: Path,
    features_path: Path,
    family_features: dict[str, tuple[str, str]],
) -> pd.DataFrame:
    event_columns = [
        "symbol", "session_date", "bar_idx", "session_return", "p1_open",
        "p2_open", "p3_open", "p5_open", "p7_open", "p8_open",
    ]
    events = pd.read_parquet(events_path, columns=event_columns)
    events["session_date"] = pd.to_datetime(events["session_date"]).dt.date
    events = events.loc[
        events["session_date"].map(lambda value: TRAIN_START <= value <= TRAIN_END)
        & events["bar_idx"].isin(DECISION_BARS)
    ].copy()
    features = pd.read_parquet(features_path)
    features["session_date"] = pd.to_datetime(features["session_date"]).dt.date
    for frame in (events, features):
        frame["event_key"] = (
            frame["symbol"].astype(str) + "|" + frame["session_date"].map(date.isoformat)
            + "|" + frame["bar_idx"].map(lambda value: f"{int(value):02d}")
        )
        if frame["event_key"].duplicated().any():
            raise RuntimeError("CBOE_DIAGNOSTIC_EVENT_KEY_DUPLICATE")
    if set(events["event_key"]) != set(features["event_key"]):
        raise RuntimeError("CBOE_DIAGNOSTIC_EVENT_KEY_COVERAGE")
    columns = ["event_key", "coverage_reason", *[item[0] for item in family_features.values()]]
    return events.merge(
        features.loc[:, columns], on="event_key", how="inner", validate="one_to_one"
    )


def run_diagnostic(
    *, events_path: Path, features_path: Path,
    expected_event_sha256: str, expected_feature_sha256: str,
    families: tuple[str, ...] = FAMILIES,
    family_features: dict[str, tuple[str, str]] = FAMILY_FEATURES,
    diagnostic_id: str = "cboe-volatility-regime-training-feasibility-v1",
    proceed_decision: str = "ACQUIRE_DEVELOPMENT_CBOE_VOLATILITY_REGIME",
    abandon_decision: str = "ABANDON_CBOE_VOLATILITY_REGIME_NO_VERSION_CREATED",
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Evaluate exactly 400 frozen training cells under immutable hashes."""
    started = time.perf_counter()
    event_sha256 = _sha256(events_path)
    feature_sha256 = _sha256(features_path)
    if event_sha256 != expected_event_sha256 or feature_sha256 != expected_feature_sha256:
        raise RuntimeError("CBOE_DIAGNOSTIC_INPUT_HASH_MISMATCH")
    merged = _validate_and_merge(events_path, features_path, family_features)
    calendar = pd.DatetimeIndex(sorted(merged["session_date"].unique()))
    records: list[dict[str, Any]] = []
    for family in families:
        merged["score"] = score_family(merged, family, family_features)
        for decision in DECISION_BARS:
            subset = merged.loc[
                merged["bar_idx"].eq(decision) & merged["score"].notna()
            ].sort_values(
                ["session_date", "score", "symbol"],
                ascending=[True, False, True], kind="stable",
            )
            subset["selection_rank"] = subset.groupby("session_date", observed=True).cumcount() + 1
            for holding in HOLDING_BARS:
                for top_count in TOP_COUNTS:
                    selected = subset.loc[subset["selection_rank"].le(top_count)]
                    standard, signal_sessions = _daily_returns(
                        selected, entry="p1_open", exit_column=STANDARD_EXITS[holding],
                        cost=0.0009, calendar=calendar,
                    )
                    stress, _ = _daily_returns(
                        selected, entry="p1_open", exit_column=STANDARD_EXITS[holding],
                        cost=0.0018, calendar=calendar,
                    )
                    delayed, _ = _daily_returns(
                        selected, entry="p2_open", exit_column=DELAY_EXITS[holding],
                        cost=0.0009, calendar=calendar,
                    )
                    standard_metrics = _metrics(standard)
                    stress_metrics = _metrics(stress)
                    delay_metrics = _metrics(delayed)
                    retained = bool(
                        signal_sessions >= 120
                        and standard_metrics["annualized_return"] >= 0.20
                        and standard_metrics["information_ratio"] >= 0.80
                        and standard_metrics["max_drawdown"] < 0.20
                        and standard_metrics["positive_calendar_years"] >= 2
                        and stress_metrics["annualized_return"] > 0
                        and delay_metrics["annualized_return"] > 0
                    )
                    records.append({
                        **asdict(Specification(family, decision, holding, top_count)),
                        "signal_sessions": signal_sessions,
                        "standard_9bp": standard_metrics,
                        "cost_18bp": stress_metrics,
                        "delay_5m_9bp": delay_metrics,
                        "retention_floor_passed": retained,
                    })
    cells = pd.DataFrame.from_records(records)
    cells["standard_annualized_return"] = cells["standard_9bp"].map(lambda value: value["annualized_return"])
    cells["standard_information_ratio"] = cells["standard_9bp"].map(lambda value: value["information_ratio"])
    retained = cells.loc[cells["retention_floor_passed"]]
    retained_families = sorted(set(retained["family"]))
    ranked = cells.sort_values(
        ["retention_floor_passed", "standard_annualized_return", "standard_information_ratio"],
        ascending=False, kind="stable",
    )
    proceed = len(retained_families) >= 2
    return cells, {
        "schema_version": "1.0.0", "status": "COMPLETE",
        "diagnostic_id": diagnostic_id,
        "period": "2021-01-01/2023-12-31", "event_sha256": event_sha256,
        "feature_sha256": feature_sha256, "event_rows": len(merged),
        "covered_event_rows": int(merged["coverage_reason"].eq("COVERED").sum()),
        "calendar_sessions": len(calendar), "cells_completed": len(cells),
        "retained_cells": len(retained), "retained_families": retained_families,
        "decision": proceed_decision if proceed else abandon_decision,
        "best_cell": ranked.iloc[0].to_dict() if not ranked.empty else None,
        "development_or_consumed_loaded": False, "strategy_versions_created": 0,
        "paper_activation": False, "order_route": "FORBIDDEN",
        "elapsed_seconds": time.perf_counter() - started,
    }
