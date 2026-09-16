"""Frozen training-only feasibility diagnostic for point-in-time news features."""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

FAMILIES = (
    "recent_attention_continuation",
    "negative_news_reversal",
    "positive_news_continuation",
    "earnings_guidance_continuation",
    "adverse_event_reversal",
)
DECISION_BARS = (2, 5, 11, 17, 23)
HOLDING_BARS = (1, 2, 4, 6)
TOP_COUNTS = (1, 3, 5, 10)
TRAIN_START = date(2021, 1, 1)
TRAIN_END = date(2023, 12, 31)
STANDARD_EXITS = {1: "p2_open", 2: "p3_open", 4: "p5_open", 6: "p7_open"}
DELAY_EXITS = {1: "p3_open", 2: "p5_open", 4: "p7_open", 6: "p8_open"}


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
        raise AssertionError("NEWS_DIAGNOSTIC_GRID_INVALID")
    return result


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _percentile(frame: pd.DataFrame, values: pd.Series) -> pd.Series:
    ranked = frame.loc[:, ["session_date", "bar_idx"]].copy()
    ranked["value"] = pd.to_numeric(values, errors="coerce")
    return ranked.groupby(["session_date", "bar_idx"], observed=True)["value"].rank(
        method="average", pct=True
    )


def score_family(frame: pd.DataFrame, family: str) -> pd.Series:
    """Compute one preregistered score from within-clock percentile ranks."""
    if family == "recent_attention_continuation":
        return _percentile(frame, frame["decayed_article_count_2h"]) + _percentile(
            frame, frame["session_return"]
        )
    if family == "negative_news_reversal":
        tone = frame["negative_count_1d"] - frame["positive_count_1d"]
        return _percentile(frame, tone) - _percentile(frame, frame["session_return"])
    if family == "positive_news_continuation":
        tone = frame["positive_count_1d"] - frame["negative_count_1d"]
        return _percentile(frame, tone) + _percentile(frame, frame["session_return"])
    if family == "earnings_guidance_continuation":
        events = frame["earnings_count_1d"] + frame["guidance_count_1d"]
        return _percentile(frame, events) + _percentile(
            frame, frame["session_return"]
        )
    if family == "adverse_event_reversal":
        events = (
            frame["financing_count_5d"]
            + frame["litigation_count_5d"]
            + frame["regulatory_count_5d"]
        )
        return _percentile(frame, events) - _percentile(
            frame, frame["session_return"]
        )
    raise ValueError(f"NEWS_DIAGNOSTIC_FAMILY_INVALID:{family}")


def _metrics(series: pd.Series) -> dict[str, float | int | dict[str, float]]:
    clean = series.fillna(0.0).astype(float)
    if clean.empty:
        return {
            "annualized_return": 0.0,
            "max_drawdown": 0.0,
            "information_ratio": 0.0,
            "positive_calendar_years": 0,
            "calendar_year_returns": {},
        }
    wealth = (1.0 + clean).cumprod()
    drawdown = wealth / wealth.cummax() - 1.0
    index = pd.DatetimeIndex(clean.index)
    year_returns = {
        str(year): float(np.prod(1.0 + clean.loc[index.year == year]) - 1.0)
        for year in sorted(set(index.year))
    }
    annualized = math.exp(
        float(np.log1p(clean.clip(lower=-0.999999)).sum()) * 252.0 / len(clean)
    ) - 1.0
    volatility = float(clean.std(ddof=1))
    return {
        "annualized_return": annualized,
        "max_drawdown": float(-drawdown.min()),
        "information_ratio": (
            float(clean.mean() / volatility * math.sqrt(252.0))
            if volatility > 0
            else 0.0
        ),
        "positive_calendar_years": sum(value > 0 for value in year_returns.values()),
        "calendar_year_returns": year_returns,
    }


def _daily_returns(
    selected: pd.DataFrame,
    *,
    entry: str,
    exit_column: str,
    cost: float,
    calendar: pd.DatetimeIndex,
) -> tuple[pd.Series, int]:
    finite = selected[entry].gt(0) & selected[exit_column].gt(0)
    tradable = selected.loc[finite]
    raw = (tradable[exit_column] / tradable[entry] - 1.0).groupby(
        tradable["session_date"], sort=True
    ).mean()
    raw.index = pd.DatetimeIndex(raw.index)
    daily = raw.reindex(calendar, fill_value=0.0)
    daily.loc[raw.index] -= cost
    return daily, len(raw)


def _validate_and_merge(events_path: Path, features_path: Path) -> pd.DataFrame:
    event_columns = [
        "symbol",
        "session_date",
        "bar_idx",
        "session_return",
        "p1_open",
        "p2_open",
        "p3_open",
        "p5_open",
        "p7_open",
        "p8_open",
    ]
    events = pd.read_parquet(events_path, columns=event_columns)
    events["session_date"] = pd.to_datetime(events["session_date"]).dt.date
    events = events.loc[
        events["session_date"].map(lambda value: TRAIN_START <= value <= TRAIN_END)
        & events["bar_idx"].isin(DECISION_BARS)
    ].copy()
    events["symbol"] = events["symbol"].astype(str)
    events["event_key"] = (
        events["symbol"]
        + "|"
        + events["session_date"].map(date.isoformat)
        + "|"
        + events["bar_idx"].map(lambda value: f"{int(value):02d}")
    )
    features = pd.read_parquet(features_path)
    if events["event_key"].duplicated().any() or features["event_key"].duplicated().any():
        raise RuntimeError("NEWS_DIAGNOSTIC_EVENT_KEY_DUPLICATE")
    features["session_date"] = pd.to_datetime(features["session_date"]).dt.date
    if not features["session_date"].map(
        lambda value: TRAIN_START <= value <= TRAIN_END
    ).all():
        raise RuntimeError("NEWS_DIAGNOSTIC_TRAINING_BOUNDARY")
    if set(events["event_key"]) != set(features["event_key"]):
        raise RuntimeError("NEWS_DIAGNOSTIC_EVENT_KEY_COVERAGE")
    feature_columns = [
        "event_key",
        "symbol",
        "session_date",
        "bar_idx",
        "decayed_article_count_2h",
        "negative_count_1d",
        "positive_count_1d",
        "earnings_count_1d",
        "guidance_count_1d",
        "financing_count_5d",
        "litigation_count_5d",
        "regulatory_count_5d",
    ]
    merged = events.merge(
        features.loc[:, feature_columns],
        on="event_key",
        how="inner",
        validate="one_to_one",
        suffixes=("_event", "_feature"),
    )
    identity_valid = (
        merged["symbol_event"].eq(merged["symbol_feature"])
        & merged["session_date_event"].eq(merged["session_date_feature"])
        & merged["bar_idx_event"].eq(merged["bar_idx_feature"])
    )
    if not identity_valid.all():
        raise RuntimeError("NEWS_DIAGNOSTIC_EVENT_IDENTITY_MISMATCH")
    return merged.rename(
        columns={
            "symbol_event": "symbol",
            "session_date_event": "session_date",
            "bar_idx_event": "bar_idx",
        }
    ).drop(columns=["symbol_feature", "session_date_feature", "bar_idx_feature"])


def run_diagnostic(
    *,
    events_path: Path,
    features_path: Path,
    expected_event_sha256: str,
    expected_feature_sha256: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Run all frozen training cells after validating exact immutable inputs."""
    started = time.perf_counter()
    event_sha256 = _sha256(events_path)
    feature_sha256 = _sha256(features_path)
    if (
        event_sha256 != expected_event_sha256
        or feature_sha256 != expected_feature_sha256
    ):
        raise RuntimeError("NEWS_DIAGNOSTIC_INPUT_HASH_MISMATCH")
    merged = _validate_and_merge(events_path, features_path)
    if merged.empty or not merged["session_date"].map(
        lambda value: TRAIN_START <= value <= TRAIN_END
    ).all():
        raise RuntimeError("NEWS_DIAGNOSTIC_TRAINING_BOUNDARY")
    calendar = pd.DatetimeIndex(sorted(merged["session_date"].unique()))
    records: list[dict[str, Any]] = []
    for family in FAMILIES:
        merged["score"] = score_family(merged, family)
        for decision in DECISION_BARS:
            subset = merged.loc[merged["bar_idx"].eq(decision)].sort_values(
                ["session_date", "score", "symbol"],
                ascending=[True, False, True],
                kind="stable",
            )
            subset["selection_rank"] = (
                subset.groupby("session_date", observed=True).cumcount() + 1
            )
            for holding in HOLDING_BARS:
                for top_count in TOP_COUNTS:
                    selected = subset.loc[subset["selection_rank"].le(top_count)]
                    standard, signal_sessions = _daily_returns(
                        selected,
                        entry="p1_open",
                        exit_column=STANDARD_EXITS[holding],
                        cost=0.0009,
                        calendar=calendar,
                    )
                    stress, _ = _daily_returns(
                        selected,
                        entry="p1_open",
                        exit_column=STANDARD_EXITS[holding],
                        cost=0.0018,
                        calendar=calendar,
                    )
                    delayed, _ = _daily_returns(
                        selected,
                        entry="p2_open",
                        exit_column=DELAY_EXITS[holding],
                        cost=0.0009,
                        calendar=calendar,
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
                    records.append(
                        {
                            **asdict(Specification(family, decision, holding, top_count)),
                            "signal_sessions": signal_sessions,
                            "standard_9bp": standard_metrics,
                            "cost_18bp": stress_metrics,
                            "delay_5m_9bp": delay_metrics,
                            "retention_floor_passed": retained,
                        }
                    )
    cells = pd.DataFrame.from_records(records)
    retained = cells.loc[cells["retention_floor_passed"].eq(True)]
    retained_families = sorted(set(retained["family"]))
    proceed = len(retained_families) >= 2
    cells["standard_annualized_return"] = cells["standard_9bp"].map(
        lambda value: value["annualized_return"]
    )
    cells["standard_information_ratio"] = cells["standard_9bp"].map(
        lambda value: value["information_ratio"]
    )
    ranked = cells.sort_values(
        ["retention_floor_passed", "standard_annualized_return", "standard_information_ratio"],
        ascending=False,
        kind="stable",
    )
    summary: dict[str, object] = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "diagnostic_id": "point-in-time-news-training-feasibility-v1",
        "period": "2021-01-01/2023-12-31",
        "event_sha256": event_sha256,
        "feature_sha256": feature_sha256,
        "event_rows": len(merged),
        "calendar_sessions": len(calendar),
        "cells_completed": len(cells),
        "retained_cells": len(retained),
        "retained_families": retained_families,
        "decision": (
            "PROCEED_TO_SEPARATE_DEVELOPMENT_ACQUISITION_PLAN"
            if proceed
            else "ABANDON_NEWS_CONTRACT_NO_VERSION_CREATED"
        ),
        "best_cell": ranked.iloc[0].to_dict() if not ranked.empty else None,
        "development_or_consumed_loaded": False,
        "strategy_versions_created": 0,
        "paper_activation": False,
        "order_route": "FORBIDDEN",
        "elapsed_seconds": time.perf_counter() - started,
    }
    return cells, summary
