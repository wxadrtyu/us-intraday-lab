"""Frozen training-only feasibility diagnostic for exact original SEC Form S-8 events."""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

FAMILIES = (
    "all_event_continuation",
    "all_event_reversal",
    "first_or_renewal_252_continuation",
    "repeat_252_continuation",
    "clustered_repeat_63_reversal",
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
        raise AssertionError("SEC_S8_GRID_INVALID")
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_coverage(
    path: Path, expected_sha256: str
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Validate and load the frozen metadata-only coverage artifact."""
    if _sha256(path) != expected_sha256:
        raise RuntimeError("SEC_S8_COVERAGE_HASH_MISMATCH")
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    coverage = payload.get("coverage", {})
    if (
        payload.get("status") != "ACCEPTANCE_COVERAGE_COMPLETE"
        or coverage.get("passed") is not True
    ):
        raise RuntimeError("SEC_S8_COVERAGE_NOT_PASSED")
    rows = pd.DataFrame(payload.get("admissible_rows", []))
    required = {
        "symbol",
        "cik",
        "accession",
        "accepted",
        "form",
        "next_sample_session",
        "admissible",
    }
    if not required.issubset(rows.columns):
        raise RuntimeError("SEC_S8_COVERAGE_SCHEMA_INVALID")
    if (
        rows.empty
        or not rows["admissible"].eq(True).all()
        or not rows["form"].eq("S-8").all()
        or rows[["symbol", "accession"]].duplicated().any()
        or rows["accepted"].isna().any()
        or rows["next_sample_session"].isna().any()
        or int(coverage.get("issuer_document_pairs", -1)) != len(rows)
    ):
        raise RuntimeError("SEC_S8_COVERAGE_ROWS_INVALID")
    rows = rows.loc[:, sorted(required)].copy()
    rows["symbol"] = rows["symbol"].astype(str)
    rows["accession"] = rows["accession"].astype(str)
    rows["next_sample_session"] = pd.to_datetime(
        rows["next_sample_session"]
    ).dt.date
    rows["accepted"] = pd.to_datetime(rows["accepted"], errors="raise")
    audit: dict[str, object] = {
        "coverage_passed": True,
        "issuer_document_pairs": len(rows),
        "distinct_issuers": int(rows["symbol"].nunique()),
        "requested": int(payload.get("acquisition", {}).get("requested", 0)),
        "missing_or_invalid": int(
            payload.get("acquisition", {}).get("missing_or_invalid", 0)
        ),
        "original_s8": int(payload.get("source", {}).get("original_s8", 0)),
        "excluded_s8_pos": int(
            payload.get("source", {}).get("excluded_s8_pos", 0)
        ),
    }
    return rows, audit


def build_event_states(
    events: pd.DataFrame, symbol_sessions: pd.DataFrame
) -> pd.DataFrame:
    """Build one causal three-session active-state row per symbol and session."""
    event_required = {"symbol", "accession", "accepted", "next_sample_session"}
    session_required = {"symbol", "session_date"}
    if not event_required.issubset(events.columns):
        raise RuntimeError("SEC_S8_EVENT_SCHEMA_INVALID")
    if not session_required.issubset(symbol_sessions.columns):
        raise RuntimeError("SEC_S8_SESSION_SCHEMA_INVALID")

    sessions = symbol_sessions.loc[:, ["symbol", "session_date"]].copy()
    sessions["symbol"] = sessions["symbol"].astype(str)
    sessions["session_date"] = pd.to_datetime(sessions["session_date"]).dt.date
    if sessions.duplicated().any():
        raise RuntimeError("SEC_S8_SYMBOL_SESSION_DUPLICATE")
    sessions = sessions.sort_values(["symbol", "session_date"], kind="stable")
    sessions["session_ordinal"] = sessions.groupby("symbol", observed=True).cumcount()

    normalized = events.loc[:, sorted(event_required)].copy()
    normalized["symbol"] = normalized["symbol"].astype(str)
    normalized["accession"] = normalized["accession"].astype(str)
    normalized["next_sample_session"] = pd.to_datetime(
        normalized["next_sample_session"]
    ).dt.date
    if normalized[["symbol", "accession"]].duplicated().any():
        raise RuntimeError("SEC_S8_EVENT_DUPLICATE")
    normalized = normalized.merge(
        sessions,
        left_on=["symbol", "next_sample_session"],
        right_on=["symbol", "session_date"],
        how="left",
        validate="many_to_one",
    )
    if normalized["session_ordinal"].isna().any():
        raise RuntimeError("SEC_S8_AVAILABILITY_SESSION_MISSING")
    normalized["session_ordinal"] = normalized["session_ordinal"].astype(int)

    positions_by_symbol = {
        symbol: sorted(set(group["session_ordinal"].astype(int)))
        for symbol, group in normalized.groupby("symbol", observed=True)
    }
    labeled_records: list[dict[str, object]] = []
    for row in normalized.sort_values(
        ["symbol", "session_ordinal", "accession"], kind="stable"
    ).to_dict("records"):
        position = int(row["session_ordinal"])
        prior = [
            value for value in positions_by_symbol[str(row["symbol"])] if value < position
        ]
        prior_252 = [value for value in prior if value >= position - 252]
        prior_63 = [value for value in prior if value >= position - 63]
        labeled_records.append(
            {
                **row,
                "first_or_renewal_252": position >= 252 and not prior_252,
                "repeat_252": bool(prior_252),
                "clustered_repeat_63": bool(prior_63),
            }
        )
    labeled = pd.DataFrame.from_records(labeled_records)

    session_lookup = {
        (str(row.symbol), int(row.session_ordinal)): row.session_date
        for row in sessions.itertuples(index=False)
    }
    active_records: list[dict[str, object]] = []
    for row in labeled.itertuples(index=False):
        for offset in range(3):
            active_date = session_lookup.get(
                (str(row.symbol), int(row.session_ordinal) + offset)
            )
            if active_date is None:
                break
            active_records.append(
                {
                    "symbol": str(row.symbol),
                    "session_date": active_date,
                    "accession": str(row.accession),
                    "first_or_renewal_252": bool(row.first_or_renewal_252),
                    "repeat_252": bool(row.repeat_252),
                    "clustered_repeat_63": bool(row.clustered_repeat_63),
                }
            )
    active = pd.DataFrame.from_records(active_records)
    if active.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "session_date",
                "active_accessions",
                "first_or_renewal_252",
                "repeat_252",
                "clustered_repeat_63",
            ]
        )
    grouped_records: list[dict[str, object]] = []
    for (symbol, session_date), group in active.groupby(
        ["symbol", "session_date"], sort=True, observed=True
    ):
        grouped_records.append(
            {
                "symbol": symbol,
                "session_date": session_date,
                "active_accessions": tuple(sorted(set(group["accession"]))),
                "first_or_renewal_252": bool(group["first_or_renewal_252"].any()),
                "repeat_252": bool(group["repeat_252"].any()),
                "clustered_repeat_63": bool(group["clustered_repeat_63"].any()),
            }
        )
    return pd.DataFrame.from_records(grouped_records).sort_values(
        ["symbol", "session_date"], kind="stable", ignore_index=True
    )


def _percentile(frame: pd.DataFrame, values: pd.Series) -> pd.Series:
    ranked = frame.loc[:, ["session_date", "bar_idx"]].copy()
    ranked["value"] = pd.to_numeric(values, errors="coerce")
    return ranked.groupby(["session_date", "bar_idx"], observed=True)["value"].rank(
        method="average", pct=True
    )


def score_family(frame: pd.DataFrame, family: str) -> pd.Series:
    """Return one frozen within-clock score and NaN for ineligible rows."""
    predicates = {
        "all_event_continuation": pd.Series(True, index=frame.index),
        "all_event_reversal": pd.Series(True, index=frame.index),
        "first_or_renewal_252_continuation": frame["first_or_renewal_252"].astype(
            bool
        ),
        "repeat_252_continuation": frame["repeat_252"].astype(bool),
        "clustered_repeat_63_reversal": frame["clustered_repeat_63"].astype(bool),
    }
    if family not in predicates:
        raise ValueError(f"SEC_S8_FAMILY_INVALID:{family}")
    eligible = predicates[family] & pd.to_numeric(
        frame["session_return"], errors="coerce"
    ).map(np.isfinite)
    score = pd.Series(np.nan, index=frame.index, dtype=float)
    if not eligible.any():
        return score
    ranked = _percentile(frame.loc[eligible], frame.loc[eligible, "session_return"])
    if family.endswith("reversal"):
        ranked = 1.0 - ranked
    score.loc[eligible] = ranked
    return score


def _metrics(series: pd.Series) -> dict[str, object]:
    clean = series.astype(float)
    if clean.isna().any():
        raise RuntimeError("SEC_S8_METRIC_MISSING_RETURN")
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
) -> tuple[pd.Series, int, bool]:
    if selected.empty:
        return pd.Series(0.0, index=calendar, dtype=float), 0, True
    entry_values = pd.to_numeric(selected[entry], errors="coerce")
    exit_values = pd.to_numeric(selected[exit_column], errors="coerce")
    finite = (
        entry_values.map(np.isfinite)
        & exit_values.map(np.isfinite)
        & entry_values.gt(0)
        & exit_values.gt(0)
    )
    if not finite.all():
        return pd.Series(0.0, index=calendar, dtype=float), 0, False
    returns = exit_values / entry_values - 1.0
    raw = returns.groupby(selected["session_date"], sort=True).mean()
    raw.index = pd.DatetimeIndex(raw.index)
    daily = raw.reindex(calendar, fill_value=0.0)
    daily.loc[raw.index] -= cost
    return daily, len(raw), True


def _load_event_cube(path: Path, expected_sha256: str) -> pd.DataFrame:
    if _sha256(path) != expected_sha256:
        raise RuntimeError("SEC_S8_EVENT_CUBE_HASH_MISMATCH")
    columns = [
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
    cube = pd.read_parquet(path, columns=columns)
    cube["symbol"] = cube["symbol"].astype(str)
    cube["session_date"] = pd.to_datetime(cube["session_date"]).dt.date
    if not cube["session_date"].map(
        lambda value: TRAIN_START <= value <= TRAIN_END
    ).all():
        raise RuntimeError("SEC_S8_TRAINING_BOUNDARY")
    cube = cube.loc[cube["bar_idx"].isin(DECISION_BARS)].copy()
    if cube[["symbol", "session_date", "bar_idx"]].duplicated().any():
        raise RuntimeError("SEC_S8_EVENT_KEY_DUPLICATE")
    return cube


def run_diagnostic(
    *,
    event_cube_path: Path,
    coverage_path: Path,
    expected_event_sha256: str,
    expected_coverage_sha256: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Evaluate all frozen training cells after validating immutable inputs."""
    started = time.perf_counter()
    coverage_rows, coverage_audit = load_coverage(
        coverage_path, expected_coverage_sha256
    )
    cube = _load_event_cube(event_cube_path, expected_event_sha256)
    symbol_sessions = cube.loc[:, ["symbol", "session_date"]].drop_duplicates()
    states = build_event_states(coverage_rows, symbol_sessions)
    active = cube.merge(
        states,
        on=["symbol", "session_date"],
        how="inner",
        validate="many_to_one",
    )
    calendar = pd.DatetimeIndex(sorted(cube["session_date"].unique()))
    records: list[dict[str, object]] = []
    for family in FAMILIES:
        family_frame = active.copy()
        family_frame["score"] = score_family(family_frame, family)
        family_frame = family_frame.loc[family_frame["score"].notna()]
        for decision in DECISION_BARS:
            subset = family_frame.loc[family_frame["bar_idx"].eq(decision)].sort_values(
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
                    standard, signal_sessions, standard_valid = _daily_returns(
                        selected,
                        entry="p1_open",
                        exit_column=STANDARD_EXITS[holding],
                        cost=0.0009,
                        calendar=calendar,
                    )
                    stress, _, stress_valid = _daily_returns(
                        selected,
                        entry="p1_open",
                        exit_column=STANDARD_EXITS[holding],
                        cost=0.0018,
                        calendar=calendar,
                    )
                    delayed, _, delay_valid = _daily_returns(
                        selected,
                        entry="p2_open",
                        exit_column=DELAY_EXITS[holding],
                        cost=0.0009,
                        calendar=calendar,
                    )
                    valid = standard_valid and stress_valid and delay_valid
                    standard_metrics = _metrics(standard)
                    stress_metrics = _metrics(stress)
                    delay_metrics = _metrics(delayed)
                    retained = bool(
                        valid
                        and signal_sessions >= 120
                        and standard_metrics["annualized_return"] >= 0.20
                        and standard_metrics["information_ratio"] >= 0.80
                        and standard_metrics["max_drawdown"] < 0.20
                        and standard_metrics["positive_calendar_years"] >= 2
                        and stress_metrics["annualized_return"] > 0
                        and delay_metrics["annualized_return"] > 0
                    )
                    records.append(
                        {
                            **asdict(
                                Specification(family, decision, holding, top_count)
                            ),
                            "valid": valid,
                            "signal_sessions": signal_sessions,
                            "standard_cost_bp": 9,
                            "stress_cost_bp": 18,
                            "delay_bars": 1,
                            "standard_9bp": standard_metrics,
                            "cost_18bp": stress_metrics,
                            "delay_1bar_9bp": delay_metrics,
                            "retention_floor_passed": retained,
                        }
                    )
    cells = pd.DataFrame.from_records(records)
    if len(cells) != 400:
        raise RuntimeError("SEC_S8_GRID_EXECUTION_INCOMPLETE")
    retained = cells.loc[cells["retention_floor_passed"].eq(True)]
    retained_families = sorted(set(retained["family"]))
    invalid_cells = int(cells["valid"].eq(False).sum())
    proceed = invalid_cells == 0 and len(retained_families) >= 2
    summary: dict[str, object] = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "diagnostic_id": "sec-original-s8-training-feasibility-v1",
        "period": "2021-01-01/2023-12-31",
        "event_cube_sha256": expected_event_sha256,
        "coverage_sha256": expected_coverage_sha256,
        "coverage": coverage_audit,
        "event_rows": len(cube),
        "active_state_rows": len(states),
        "calendar_sessions": len(calendar),
        "cells_completed": len(cells),
        "invalid_cells": invalid_cells,
        "retained_cells": len(retained),
        "retained_families": retained_families,
        "decision": (
            "ACQUIRE_DEVELOPMENT_SEC_S8_DATA"
            if proceed
            else "ABANDON_SEC_S8_NO_VERSION_CREATED"
        ),
        "strategy_versions_created": 0,
        "development_or_consumed_loaded": False,
        "primary_document_bodies_opened": False,
        "paper_activation": False,
        "order_route": "FORBIDDEN",
        "runtime_seconds": time.perf_counter() - started,
    }
    return cells, summary
