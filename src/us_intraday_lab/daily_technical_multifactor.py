"""Frozen training-only daily technical multi-factor diagnostic."""

from __future__ import annotations

import hashlib
import math
import re
import time
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

FAMILIES = (
    "balanced_trend",
    "residual_trend",
    "quiet_pullback",
    "volume_confirmed_trend",
    "defensive_momentum",
)
DECISION_BARS = (2, 5, 11, 17, 23)
HOLDING_BARS = (1, 2, 4, 6)
TOP_COUNTS = (5, 10, 20, 40)
STANDARD_EXITS = {1: "p2_open", 2: "p3_open", 4: "p5_open", 6: "p7_open"}
DELAY_EXITS = {1: "p3_open", 2: "p5_open", 4: "p7_open", 6: "p8_open"}
TRAIN_START = date(2021, 1, 1)
TRAIN_END = date(2023, 12, 31)
SOURCE_START_MONTH = "2020-07"
SOURCE_END_MONTH = "2023-12"

PRIMITIVES = {
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
    "quiet_pullback": (
        ("momentum_60_5", 1.0),
        ("reversal_5", 1.0),
        ("drawdown_60", 1.0),
        ("downside_volatility_20", -1.0),
    ),
    "volume_confirmed_trend": (
        ("momentum_20_5", 1.0),
        ("momentum_60_5", 1.0),
        ("volume_confirmation", 1.0),
        ("trend_efficiency_20", 1.0),
        ("realized_volatility_20", -1.0),
    ),
    "defensive_momentum": (
        ("momentum_60_5", 1.0),
        ("residual_momentum_60_5", 1.0),
        ("drawdown_60", 1.0),
        ("downside_volatility_20", -1.0),
        ("realized_volatility_20", -1.0),
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
        raise AssertionError("DAILY_TECHNICAL_GRID_INVALID")
    return result


def _validate_daily_bars(daily_bars: pd.DataFrame) -> pd.DataFrame:
    required = {"symbol", "session_date", "open", "high", "low", "close", "volume"}
    if not required.issubset(daily_bars.columns):
        raise ValueError("DAILY_TECHNICAL_DAILY_SCHEMA_INVALID")
    frame = daily_bars.loc[:, sorted(required)].copy()
    frame["symbol"] = frame["symbol"].astype(str)
    frame["session_date"] = pd.to_datetime(frame["session_date"]).astype("datetime64[ns]")
    if frame[["symbol", "session_date"]].duplicated().any():
        raise ValueError("DAILY_TECHNICAL_DAILY_KEY_DUPLICATE")
    numeric = ("open", "high", "low", "close", "volume")
    for column in numeric:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    finite = np.isfinite(frame.loc[:, numeric]).all(axis=1)
    prices_positive = frame.loc[:, ("open", "high", "low", "close")].gt(0).all(axis=1)
    if not finite.all() or not prices_positive.all() or not frame["volume"].ge(0).all():
        raise ValueError("DAILY_TECHNICAL_DAILY_VALUES_INVALID")
    return frame.sort_values(["symbol", "session_date"], kind="stable", ignore_index=True)


def build_daily_features(daily_bars: pd.DataFrame) -> pd.DataFrame:
    """Build the preregistered primitives from completed daily bars."""
    frame = _validate_daily_bars(daily_bars)
    frame["log_close"] = np.log(frame["close"])
    grouped = frame.groupby("symbol", sort=False, observed=True)
    frame["lr"] = grouped["log_close"].diff()
    frame["market_lr"] = frame.groupby("session_date", observed=True)["lr"].transform(
        "median"
    )
    frame["residual_lr"] = frame["lr"] - frame["market_lr"]

    grouped = frame.groupby("symbol", sort=False, observed=True)
    frame["momentum_20_5"] = grouped["log_close"].shift(5) - grouped["log_close"].shift(20)
    frame["momentum_60_5"] = grouped["log_close"].shift(5) - grouped["log_close"].shift(60)
    frame["reversal_5"] = -(frame["log_close"] - grouped["log_close"].shift(5))
    abs_path = grouped["lr"].transform(
        lambda values: values.abs().rolling(20, min_periods=20).sum()
    )
    frame["trend_efficiency_20"] = (
        (frame["log_close"] - grouped["log_close"].shift(20)).abs() / abs_path
    ).where(abs_path.gt(0))
    frame["realized_volatility_20"] = grouped["lr"].transform(
        lambda values: values.rolling(20, min_periods=20).std(ddof=1)
    ) * math.sqrt(252.0)
    downside = frame["lr"].clip(upper=0.0).pow(2)
    frame["downside_volatility_20"] = (
        downside.groupby(frame["symbol"], sort=False, observed=True)
        .transform(lambda values: values.rolling(20, min_periods=20).mean())
        .pow(0.5)
        * math.sqrt(252.0)
    )
    rolling_high = grouped["close"].transform(
        lambda values: values.rolling(60, min_periods=60).max()
    )
    frame["drawdown_60"] = frame["close"] / rolling_high - 1.0
    volume_5 = grouped["volume"].transform(
        lambda values: values.rolling(5, min_periods=5).mean()
    )
    volume_20 = grouped["volume"].transform(
        lambda values: values.rolling(20, min_periods=20).mean()
    )
    volume_ratio = (volume_5 / volume_20).where(volume_20.gt(0) & volume_5.gt(0))
    frame["volume_confirmation"] = np.sign(frame["momentum_20_5"]) * np.log(volume_ratio)
    shifted_residual = grouped["residual_lr"].shift(5)
    frame["residual_momentum_60_5"] = (
        shifted_residual.groupby(frame["symbol"], sort=False, observed=True)
        .transform(lambda values: values.rolling(55, min_periods=55).sum())
    )
    frame = frame.rename(columns={"session_date": "feature_date"})
    primitive_names = sorted({name for family in PRIMITIVES.values() for name, _ in family})
    return frame.loc[:, ["symbol", "feature_date", *primitive_names]]


def map_features_to_sessions(
    features: pd.DataFrame, sessions: pd.DataFrame
) -> pd.DataFrame:
    """Map only a strictly earlier completed feature row to each execution session."""
    required_features = {"symbol", "feature_date"}
    required_sessions = {"symbol", "session_date"}
    if not required_features.issubset(features.columns) or not required_sessions.issubset(
        sessions.columns
    ):
        raise ValueError("DAILY_TECHNICAL_MAPPING_SCHEMA_INVALID")
    right = features.copy()
    left = sessions.loc[:, ["symbol", "session_date"]].copy()
    right["feature_date"] = pd.to_datetime(right["feature_date"]).astype("datetime64[ns]")
    left["session_date"] = pd.to_datetime(left["session_date"]).astype("datetime64[ns]")
    value_columns = [column for column in right.columns if column not in required_features]
    pieces: list[pd.DataFrame] = []
    for symbol, symbol_sessions in left.groupby("symbol", sort=False, observed=True):
        history = right.loc[right["symbol"].eq(symbol), ["feature_date", *value_columns]]
        history = history.sort_values("feature_date", kind="stable")
        ordered_sessions = symbol_sessions.sort_values("session_date", kind="stable")
        if history.empty:
            mapped = ordered_sessions.copy()
            mapped["feature_date"] = pd.NaT
            for column in value_columns:
                mapped[column] = np.nan
        else:
            mapped = pd.merge_asof(
                ordered_sessions,
                history,
                left_on="session_date",
                right_on="feature_date",
                direction="backward",
                allow_exact_matches=False,
            )
        mapped["symbol"] = symbol
        pieces.append(mapped)
    if not pieces:
        return pd.DataFrame(columns=["symbol", "session_date", "feature_date", *value_columns])
    return pd.concat(pieces, ignore_index=True).sort_values(
        ["session_date", "symbol"], kind="stable", ignore_index=True
    )


def score_family(frame: pd.DataFrame, family: str) -> pd.Series:
    """Return the equal-weight oriented percentile-rank composite."""
    if family not in PRIMITIVES:
        raise ValueError(f"DAILY_TECHNICAL_UNKNOWN_FAMILY:{family}")
    ranks = []
    for column, direction in PRIMITIVES[family]:
        if column not in frame.columns:
            raise ValueError(f"DAILY_TECHNICAL_PRIMITIVE_MISSING:{column}")
        oriented = frame[column] * direction
        ranks.append(
            oriented.groupby(frame["session_date"], observed=True).rank(
                method="average", pct=True
            )
        )
    return pd.concat(ranks, axis=1).mean(axis=1, skipna=False)


def _metrics(daily: pd.Series) -> dict[str, object]:
    clean = daily.astype(float)
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


def daily_returns(
    selected: pd.DataFrame,
    *,
    entry: str,
    exit_column: str,
    cost: float,
    calendar: pd.DatetimeIndex,
) -> tuple[pd.Series, int, bool]:
    """Aggregate an equal-weight selected portfolio, failing closed on bad prices."""
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
    raw = (exit_values / entry_values - 1.0).groupby(selected["session_date"], sort=True).mean()
    raw.index = pd.DatetimeIndex(raw.index)
    daily = raw.reindex(calendar, fill_value=0.0)
    daily.loc[raw.index] -= cost
    return daily, len(raw), True


def evaluate_grid(feature_scores: pd.DataFrame, event_cube: pd.DataFrame) -> pd.DataFrame:
    """Evaluate every preregistered family/decision/holding/top-count cell."""
    score_required = {"symbol", "session_date", *FAMILIES}
    price_columns = {"p1_open", "p2_open", "p3_open", "p5_open", "p7_open", "p8_open"}
    cube_required = {"symbol", "session_date", "bar_idx", *price_columns}
    if not score_required.issubset(feature_scores.columns) or not cube_required.issubset(
        event_cube.columns
    ):
        raise ValueError("DAILY_TECHNICAL_GRID_SCHEMA_INVALID")
    scores = feature_scores.loc[:, sorted(score_required)].copy()
    cube = event_cube.loc[:, sorted(cube_required)].copy()
    scores["session_date"] = pd.to_datetime(scores["session_date"]).astype("datetime64[ns]")
    cube["session_date"] = pd.to_datetime(cube["session_date"]).astype("datetime64[ns]")
    if scores[["symbol", "session_date"]].duplicated().any():
        raise ValueError("DAILY_TECHNICAL_SCORE_KEY_DUPLICATE")
    if cube[["symbol", "session_date", "bar_idx"]].duplicated().any():
        raise ValueError("DAILY_TECHNICAL_EVENT_KEY_DUPLICATE")
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
        raise RuntimeError("DAILY_TECHNICAL_GRID_EXECUTION_INCOMPLETE")
    return cells


def training_decision(cells: pd.DataFrame) -> str:
    retained = cells.loc[cells["retention_floor_passed"].eq(True)]
    families = set(retained["family"])
    if int(cells["valid"].eq(False).sum()) == 0 and len(families) >= 2:
        return "ACQUIRE_DEVELOPMENT_DAILY_TECHNICAL_DATA"
    return "ABANDON_DAILY_TECHNICAL_NO_VERSION_CREATED"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _daily_source_files(root: Path) -> list[Path]:
    matched: list[Path] = []
    pattern = re.compile(r"^(\d{4}-\d{2})-.*\.(json|parquet)$")
    for path in root.iterdir():
        match = pattern.match(path.name)
        if match and SOURCE_START_MONTH <= match.group(1) <= SOURCE_END_MONTH:
            matched.append(path)
    matched.sort(key=lambda path: path.name)
    suffix_counts = {suffix: sum(path.suffix == suffix for path in matched) for suffix in (".json", ".parquet")}
    if suffix_counts != {".json": 672, ".parquet": 672}:
        raise RuntimeError(f"DAILY_TECHNICAL_SOURCE_FILE_SET_INVALID:{suffix_counts}")
    return matched


def _tree_sha256(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        size = path.stat().st_size
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(_file_sha256(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _load_event_cube(path: Path, expected_sha256: str) -> tuple[pd.DataFrame, int]:
    if _file_sha256(path) != expected_sha256:
        raise RuntimeError("DAILY_TECHNICAL_EVENT_CUBE_HASH_MISMATCH")
    all_dates = pd.to_datetime(pd.read_parquet(path, columns=["session_date"])["session_date"])
    in_training = all_dates.dt.date.map(lambda value: TRAIN_START <= value <= TRAIN_END)
    columns = [
        "symbol",
        "session_date",
        "bar_idx",
        "p1_open",
        "p2_open",
        "p3_open",
        "p5_open",
        "p7_open",
        "p8_open",
    ]
    cube = pd.read_parquet(
        path,
        columns=columns,
        filters=[("session_date", ">=", TRAIN_START), ("session_date", "<=", TRAIN_END)],
    )
    cube["session_date"] = pd.to_datetime(cube["session_date"]).astype("datetime64[ns]")
    cube = cube.loc[cube["bar_idx"].isin(DECISION_BARS)].copy()
    if cube.empty or cube[["symbol", "session_date", "bar_idx"]].duplicated().any():
        raise RuntimeError("DAILY_TECHNICAL_EVENT_CUBE_INVALID")
    return cube, int((~in_training).sum())


def _load_daily_bars(paths: list[Path], symbols: pd.DataFrame) -> pd.DataFrame:
    parquet_paths = [str(path) for path in paths if path.suffix == ".parquet"]
    connection = duckdb.connect()
    try:
        connection.register("sample_symbols", symbols.loc[:, ["symbol"]].drop_duplicates())
        return connection.execute(
            """
            SELECT d.symbol,
                   CAST(d.timestamp AS DATE) AS session_date,
                   d.open, d.high, d.low, d.close, d.volume
            FROM read_parquet(?, union_by_name=true) AS d
            INNER JOIN sample_symbols AS s USING (symbol)
            WHERE CAST(d.timestamp AS DATE) BETWEEN DATE '2020-07-01' AND DATE '2023-12-29'
            ORDER BY d.symbol, session_date
            """,
            [parquet_paths],
        ).df()
    finally:
        connection.close()


def run_diagnostic(
    *,
    daily_root: Path,
    event_cube_path: Path,
    expected_daily_sha256: str,
    expected_event_sha256: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Validate immutable inputs and evaluate the frozen training grid."""
    started = time.perf_counter()
    source_files = _daily_source_files(daily_root)
    actual_daily_sha256 = _tree_sha256(source_files)
    if actual_daily_sha256 != expected_daily_sha256:
        raise RuntimeError("DAILY_TECHNICAL_DAILY_SOURCE_HASH_MISMATCH")
    cube, excluded_outside_training = _load_event_cube(
        event_cube_path, expected_event_sha256
    )
    sample_symbols = cube.loc[:, ["symbol"]].drop_duplicates()
    daily_bars = _load_daily_bars(source_files, sample_symbols)
    primitives = build_daily_features(daily_bars)
    sessions = cube.loc[:, ["symbol", "session_date"]].drop_duplicates()
    mapped = map_features_to_sessions(primitives, sessions)
    for family in FAMILIES:
        mapped[family] = score_family(mapped, family)
    score_frame = mapped.loc[:, ["symbol", "session_date", *FAMILIES]]
    cells = evaluate_grid(score_frame, cube)
    retained = cells.loc[cells["retention_floor_passed"].eq(True)]
    retained_families = sorted(set(retained["family"]))
    eligible = mapped.loc[:, list(FAMILIES)].notna().all(axis=1)
    coverage_by_year = {
        str(year): {
            "pairs": len(group),
            "symbols": int(group["symbol"].nunique()),
            "sessions": int(group["session_date"].nunique()),
        }
        for year, group in mapped.loc[eligible].groupby(mapped.loc[eligible, "session_date"].dt.year)
    }
    summary: dict[str, object] = {
        "schema_version": "1.0.0",
        "status": "COMPLETE",
        "diagnostic_id": "daily-technical-multifactor-training-v1",
        "period": "2021-01-01/2023-12-31",
        "sample_scope": "527-symbol coverage-limited sample; not full market",
        "daily_source_sha256": expected_daily_sha256,
        "daily_source_files": len(source_files),
        "daily_source_bytes": sum(path.stat().st_size for path in source_files),
        "event_cube_sha256": expected_event_sha256,
        "event_rows": len(cube),
        "container_rows_excluded_outside_training": excluded_outside_training,
        "eligible_symbol_sessions": int(eligible.sum()),
        "eligible_symbols": int(mapped.loc[eligible, "symbol"].nunique()),
        "calendar_sessions": int(mapped["session_date"].nunique()),
        "coverage_by_year": coverage_by_year,
        "cells_completed": len(cells),
        "invalid_cells": int(cells["valid"].eq(False).sum()),
        "retained_cells": len(retained),
        "retained_families": retained_families,
        "decision": training_decision(cells),
        "strategy_versions_created": 0,
        "development_or_consumed_loaded": False,
        "paper_activation": False,
        "order_route": "FORBIDDEN",
        "runtime_seconds": time.perf_counter() - started,
    }
    return cells, summary
