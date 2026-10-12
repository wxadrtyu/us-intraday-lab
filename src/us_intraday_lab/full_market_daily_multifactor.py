"""Frozen full-market long-horizon daily technical multifactor contract."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

FAMILIES = (
    "residual_momentum",
    "trend_quality",
    "low_vol_trend",
    "liquidity_confirmed_breakout",
    "trend_conditioned_reversal",
)
REBALANCE_SESSIONS = (5, 10, 20, 21)
HOLDING_SESSIONS = (5, 10, 20, 42)
TOP_COUNTS = (10, 20, 40, 80, 120)

_DAILY_COLUMNS = {
    "symbol",
    "session_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
    "trade_count",
}
_UNIVERSE_COLUMNS = {"symbol", "month", "information_cutoff", "eligible"}


@dataclass(frozen=True, slots=True)
class Specification:
    family: str
    rebalance_sessions: int
    holding_sessions: int
    top_count: int


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    name: str
    daily_returns: pd.Series
    valid: bool
    invalid_reason: str | None
    cohorts: int
    selection_sha256: str


@dataclass(frozen=True, slots=True)
class RunIdentity:
    daily_source_sha256: str
    universe_sha256: str
    design_sha256: str
    code_sha256: str
    gate_sha256: str

    def validate(self) -> None:
        for name, value in asdict(self).items():
            if re.fullmatch(r"[0-9a-f]{64}", value) is None:
                raise ValueError(f"FULL_MARKET_DAILY_IDENTITY_HASH_INVALID:{name}")

    @property
    def sha256(self) -> str:
        self.validate()
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass(slots=True)
class AtomicCheckpoint:
    path: Path
    identity: RunIdentity
    total_cells: int
    cells_completed: int
    chain_sha256: str

    @classmethod
    def open(
        cls, path: Path, identity: RunIdentity, *, total_cells: int
    ) -> AtomicCheckpoint:
        identity.validate()
        if total_cells <= 0:
            raise ValueError("FULL_MARKET_DAILY_CHECKPOINT_TOTAL_INVALID")
        if path.exists():
            state = json.loads(path.read_text("utf-8"))
            if (
                state.get("identity") != asdict(identity)
                or state.get("identity_sha256") != identity.sha256
                or state.get("total_cells") != total_cells
            ):
                raise RuntimeError("FULL_MARKET_DAILY_CHECKPOINT_IDENTITY_MISMATCH")
            cells_completed = state.get("cells_completed")
            chain_sha256 = state.get("chain_sha256")
            if (
                not isinstance(cells_completed, int)
                or not 0 <= cells_completed <= total_cells
                or not isinstance(chain_sha256, str)
                or re.fullmatch(r"[0-9a-f]{64}", chain_sha256) is None
            ):
                raise RuntimeError("FULL_MARKET_DAILY_CHECKPOINT_STATE_INVALID")
            return cls(path, identity, total_cells, cells_completed, chain_sha256)
        checkpoint = cls(
            path,
            identity,
            total_cells,
            0,
            hashlib.sha256(b"").hexdigest(),
        )
        checkpoint._write()
        return checkpoint

    def _write(self) -> None:
        state = {
            "schema_version": "1.0.0",
            "identity": asdict(self.identity),
            "identity_sha256": self.identity.sha256,
            "total_cells": self.total_cells,
            "cells_completed": self.cells_completed,
            "chain_sha256": self.chain_sha256,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        temporary.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", "utf-8")
        os.replace(temporary, self.path)

    def record_cell(self, cell_index: int, result_sha256: str) -> None:
        if cell_index != self.cells_completed or cell_index >= self.total_cells:
            raise RuntimeError("FULL_MARKET_DAILY_CHECKPOINT_CELL_ORDER_INVALID")
        if re.fullmatch(r"[0-9a-f]{64}", result_sha256) is None:
            raise ValueError("FULL_MARKET_DAILY_CHECKPOINT_RESULT_HASH_INVALID")
        digest = hashlib.sha256()
        digest.update(bytes.fromhex(self.chain_sha256))
        digest.update(cell_index.to_bytes(8, byteorder="big", signed=False))
        digest.update(bytes.fromhex(result_sha256))
        self.chain_sha256 = digest.hexdigest()
        self.cells_completed += 1
        self._write()


def specifications() -> tuple[Specification, ...]:
    """Return the immutable 400-cell discovery grid."""
    result = tuple(
        Specification(family, rebalance, holding, top_count)
        for family in FAMILIES
        for rebalance in REBALANCE_SESSIONS
        for holding in HOLDING_SESSIONS
        for top_count in TOP_COUNTS
    )
    if len(result) != 400 or len(set(result)) != 400:
        raise AssertionError("FULL_MARKET_DAILY_GRID_INVALID")
    return result


def _month_start(values: pd.Series) -> pd.Series:
    timestamps = pd.to_datetime(values, errors="raise")
    return timestamps.dt.to_period("M").dt.to_timestamp()


def validate_monthly_universe(universe: pd.DataFrame) -> pd.DataFrame:
    """Validate one causal point-in-time decision for every symbol-month."""
    missing = _UNIVERSE_COLUMNS.difference(universe.columns)
    if missing:
        raise ValueError(f"FULL_MARKET_DAILY_UNIVERSE_SCHEMA_MISSING:{sorted(missing)}")
    result = universe.copy()
    result["symbol"] = result["symbol"].astype(str).str.upper()
    if result["symbol"].eq("").any():
        raise ValueError("FULL_MARKET_DAILY_UNIVERSE_SYMBOL_INVALID")
    parsed_month = pd.to_datetime(result["month"], errors="raise")
    result["month"] = _month_start(result["month"])
    if not parsed_month.eq(result["month"]).all():
        raise ValueError("FULL_MARKET_DAILY_UNIVERSE_MONTH_NOT_FIRST")
    result["information_cutoff"] = pd.to_datetime(
        result["information_cutoff"], errors="raise"
    ).dt.normalize()
    if result[["symbol", "month"]].duplicated().any():
        raise ValueError("FULL_MARKET_DAILY_UNIVERSE_KEY_DUPLICATE")
    if result["information_cutoff"].ge(result["month"]).any():
        raise ValueError("FULL_MARKET_DAILY_UNIVERSE_CUTOFF_NOT_PRIOR")
    if not result["eligible"].map(lambda value: isinstance(value, (bool, np.bool_))).all():
        raise ValueError("FULL_MARKET_DAILY_UNIVERSE_ELIGIBLE_NOT_BOOLEAN")
    return result.sort_values(["month", "symbol"], kind="stable", ignore_index=True)


def _validate_daily_bars(daily_bars: pd.DataFrame) -> pd.DataFrame:
    missing = _DAILY_COLUMNS.difference(daily_bars.columns)
    if missing:
        raise ValueError(f"FULL_MARKET_DAILY_SCHEMA_MISSING:{sorted(missing)}")
    extras = set(daily_bars.columns).difference(_DAILY_COLUMNS)
    if extras:
        raise ValueError(f"FULL_MARKET_DAILY_FORBIDDEN_INPUT_COLUMN:{sorted(extras)}")
    result = daily_bars.copy()
    result["symbol"] = result["symbol"].astype(str).str.upper()
    result["session_date"] = pd.to_datetime(
        result["session_date"], errors="raise"
    ).dt.normalize()
    if result[["symbol", "session_date"]].duplicated().any():
        raise ValueError("FULL_MARKET_DAILY_KEY_DUPLICATE")
    numeric = ["open", "high", "low", "close", "volume", "vwap", "trade_count"]
    for column in numeric:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    finite = np.isfinite(result[numeric]).all(axis=1)
    positive = result[["open", "high", "low", "close", "vwap"]].gt(0).all(axis=1)
    nonnegative = result[["volume", "trade_count"]].ge(0).all(axis=1)
    if not finite.all() or not positive.all() or not nonnegative.all():
        raise ValueError("FULL_MARKET_DAILY_VALUES_INVALID")
    return result.sort_values(["session_date", "symbol"], kind="stable", ignore_index=True)


def attach_point_in_time_eligibility(
    daily_bars: pd.DataFrame, universe: pd.DataFrame
) -> pd.DataFrame:
    """Attach only the same-month frozen decision and return eligible rows.

    A missing symbol-month decision is a source-contract failure, not an
    opportunity to infer membership or silently remove a bar.
    """
    bars = _validate_daily_bars(daily_bars)
    decisions = validate_monthly_universe(universe)
    bars["universe_month"] = _month_start(bars["session_date"])
    membership = decisions.loc[
        :, ["symbol", "month", "information_cutoff", "eligible"]
    ].rename(columns={"month": "universe_month"})
    attached = bars.merge(
        membership,
        on=["symbol", "universe_month"],
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    if attached["_merge"].ne("both").any():
        raise ValueError("FULL_MARKET_DAILY_UNIVERSE_DECISION_MISSING")
    attached = attached.drop(columns="_merge")
    return attached.loc[attached["eligible"]].sort_values(
        ["session_date", "symbol"], kind="stable", ignore_index=True
    )


def _rolling_trend(values: pd.Series, window: int) -> tuple[np.ndarray, np.ndarray]:
    array = values.to_numpy(dtype=float)
    slopes = np.full(len(array), np.nan)
    residual_volatility = np.full(len(array), np.nan)
    if len(array) < window:
        return slopes, residual_volatility
    x = np.arange(window, dtype=float)
    centered_x = x - x.mean()
    sum_x_squared = float(np.square(centered_x).sum())
    valid_slopes = np.correlate(array, centered_x, mode="valid") / sum_x_squared
    rolling_sum = np.convolve(array, np.ones(window), mode="valid")
    rolling_square_sum = np.convolve(np.square(array), np.ones(window), mode="valid")
    centered_sum_squares = rolling_square_sum - np.square(rolling_sum) / window
    residual_sum_squares = np.maximum(
        centered_sum_squares - np.square(valid_slopes) * sum_x_squared, 0.0
    )
    slopes[window - 1 :] = valid_slopes
    residual_volatility[window - 1 :] = np.sqrt(
        residual_sum_squares / (window - 2)
    )
    return slopes, residual_volatility


def build_daily_features(daily_bars: pd.DataFrame) -> pd.DataFrame:
    """Build causal completed-bar primitives before applying eligibility."""
    frame = _validate_daily_bars(daily_bars)
    frame = frame.sort_values(["symbol", "session_date"], kind="stable", ignore_index=True)
    frame["log_close"] = np.log(frame["close"])
    grouped = frame.groupby("symbol", sort=False, observed=True)
    frame["log_return"] = grouped["log_close"].diff()
    frame["market_return"] = frame.groupby("session_date", observed=True)[
        "log_return"
    ].transform("median")

    grouped = frame.groupby("symbol", sort=False, observed=True)
    frame["return_5"] = frame["log_close"] - grouped["log_close"].shift(5)
    frame["return_126"] = frame["log_close"] - grouped["log_close"].shift(126)
    frame["return_252_21"] = grouped["log_close"].shift(21) - grouped[
        "log_close"
    ].shift(252)
    market_by_date = (
        frame.loc[:, ["session_date", "market_return"]]
        .drop_duplicates("session_date")
        .sort_values("session_date", kind="stable")
    )
    market_by_date["market_return_252_21"] = (
        market_by_date["market_return"].shift(21).rolling(231, min_periods=231).sum()
    )
    frame = frame.merge(
        market_by_date.loc[:, ["session_date", "market_return_252_21"]],
        on="session_date",
        how="left",
        validate="many_to_one",
    )
    grouped = frame.groupby("symbol", sort=False, observed=True)
    rolling_covariance = grouped.apply(
        lambda group: group["log_return"].rolling(60, min_periods=60).cov(
            group["market_return"]
        ),
        include_groups=False,
    ).reset_index(level=0, drop=True)
    rolling_market_variance = grouped["market_return"].transform(
        lambda values: values.rolling(60, min_periods=60).var(ddof=1)
    )
    frame["beta_60"] = (rolling_covariance / rolling_market_variance).where(
        rolling_market_variance.gt(0)
    )
    frame["realized_volatility_60"] = grouped["log_return"].transform(
        lambda values: values.rolling(60, min_periods=60).std(ddof=1)
    ) * np.sqrt(252.0)
    frame["residual_momentum_252_21"] = (
        frame["return_252_21"]
        - frame["beta_60"] * frame["market_return_252_21"]
    ) / frame["realized_volatility_60"].where(frame["realized_volatility_60"].gt(0))

    slope = np.full(len(frame), np.nan)
    residual_volatility = np.full(len(frame), np.nan)
    for positions in grouped.indices.values():
        ordered_positions = np.asarray(positions, dtype=int)
        symbol_slope, symbol_residual = _rolling_trend(
            frame.loc[ordered_positions, "log_close"], 126
        )
        slope[ordered_positions] = symbol_slope
        residual_volatility[ordered_positions] = symbol_residual
    frame["trend_slope_126"] = slope
    frame["trend_residual_volatility_126"] = residual_volatility
    moving_average_63 = grouped["close"].transform(
        lambda values: values.rolling(63, min_periods=63).mean()
    )
    above_average = frame["close"].gt(moving_average_63).astype(float)
    frame["above_average_fraction_63"] = above_average.groupby(
        frame["symbol"], sort=False, observed=True
    ).transform(lambda values: values.rolling(63, min_periods=63).mean())
    frame["trend_quality_126"] = (
        frame["trend_slope_126"]
        / frame["trend_residual_volatility_126"].where(
            frame["trend_residual_volatility_126"].gt(0)
        )
        * frame["above_average_fraction_63"]
    )
    frame["moving_average_126"] = grouped["close"].transform(
        lambda values: values.rolling(126, min_periods=126).mean()
    )
    prior_high = grouped["close"].transform(
        lambda values: values.shift(1).rolling(126, min_periods=126).max()
    )
    frame["breakout_126"] = frame["close"] / prior_high - 1.0
    dollar_volume = frame["close"] * frame["volume"]
    frame["dollar_volume_ratio_20_126"] = (
        dollar_volume.groupby(frame["symbol"], sort=False, observed=True).transform(
            lambda values: values.rolling(20, min_periods=20).mean()
        )
        / dollar_volume.groupby(frame["symbol"], sort=False, observed=True).transform(
            lambda values: values.rolling(126, min_periods=126).median()
        )
    )
    rolling_vwap = grouped["vwap"].transform(
        lambda values: values.rolling(20, min_periods=20).mean()
    )
    frame["vwap_displacement_20"] = frame["close"] / rolling_vwap - 1.0
    output_columns = [
        "symbol",
        "session_date",
        "residual_momentum_252_21",
        "trend_quality_126",
        "return_126",
        "realized_volatility_60",
        "breakout_126",
        "dollar_volume_ratio_20_126",
        "vwap_displacement_20",
        "return_5",
        "moving_average_126",
        "close",
    ]
    return frame.loc[:, output_columns].sort_values(
        ["session_date", "symbol"], kind="stable", ignore_index=True
    )


def _winsorized_rank(values: pd.Series, dates: pd.Series) -> pd.Series:
    lower = values.groupby(dates, observed=True).transform(lambda group: group.quantile(0.01))
    upper = values.groupby(dates, observed=True).transform(lambda group: group.quantile(0.99))
    clipped = values.clip(lower=lower, upper=upper)
    return clipped.groupby(dates, observed=True).rank(method="average", pct=True)


def score_families(features: pd.DataFrame) -> pd.DataFrame:
    """Create the five preregistered cross-sectional family scores."""
    required = {
        "symbol",
        "session_date",
        "residual_momentum_252_21",
        "trend_quality_126",
        "return_126",
        "realized_volatility_60",
        "breakout_126",
        "dollar_volume_ratio_20_126",
        "vwap_displacement_20",
        "return_5",
        "moving_average_126",
        "close",
    }
    missing = required.difference(features.columns)
    if missing:
        raise ValueError(f"FULL_MARKET_DAILY_FEATURE_SCHEMA_MISSING:{sorted(missing)}")
    result = features.copy()
    dates = pd.to_datetime(result["session_date"], errors="raise").dt.normalize()
    result["session_date"] = dates
    result["residual_momentum"] = _winsorized_rank(
        result["residual_momentum_252_21"], dates
    )
    result["trend_quality"] = _winsorized_rank(result["trend_quality_126"], dates)
    positive_trend = result["return_126"].gt(0)
    trend_rank = _winsorized_rank(result["return_126"], dates)
    quiet_rank = _winsorized_rank(-result["realized_volatility_60"], dates)
    result["low_vol_trend"] = ((trend_rank + quiet_rank) / 2.0).where(positive_trend)
    volume_confirmed = result["dollar_volume_ratio_20_126"].gt(1.0)
    vwap_confirmed = result["vwap_displacement_20"].gt(0.0)
    result["liquidity_confirmed_breakout"] = (
        (
            _winsorized_rank(result["breakout_126"], dates)
            + _winsorized_rank(result["dollar_volume_ratio_20_126"], dates)
            + _winsorized_rank(result["vwap_displacement_20"], dates)
        )
        / 3.0
    ).where(volume_confirmed & vwap_confirmed)
    reversal_gate = positive_trend & result["close"].gt(result["moving_average_126"])
    result["trend_conditioned_reversal"] = _winsorized_rank(
        -result["return_5"], dates
    ).where(reversal_gate)
    return result


def _selection_rows(
    panel: pd.DataFrame, spec: Specification, calendar: pd.DatetimeIndex
) -> pd.DataFrame:
    latest_signal_ordinal = len(calendar) - spec.holding_sessions - 2
    if latest_signal_ordinal < 0:
        return pd.DataFrame(columns=["signal_date", "symbol", "selection_rank"])
    signal_dates = set(calendar[: latest_signal_ordinal + 1 : spec.rebalance_sessions])
    candidates = panel.loc[
        panel["session_date"].isin(signal_dates) & panel[spec.family].notna(),
        ["symbol", "session_date", spec.family],
    ].sort_values(
        ["session_date", spec.family, "symbol"],
        ascending=[True, False, True],
        kind="stable",
    )
    candidates["selection_rank"] = (
        candidates.groupby("session_date", observed=True).cumcount() + 1
    )
    counts = candidates.groupby("session_date", observed=True)["symbol"].transform("size")
    selected = candidates.loc[
        counts.ge(spec.top_count) & candidates["selection_rank"].le(spec.top_count)
    ].rename(columns={"session_date": "signal_date"})
    return selected.loc[:, ["signal_date", "symbol", "selection_rank"]].reset_index(drop=True)


def _selection_sha256(selected: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    for row in selected.itertuples(index=False):
        digest.update(
            f"{row.signal_date.isoformat()}|{row.selection_rank}|{row.symbol}\n".encode()
        )
    return digest.hexdigest()


def _scenario_result(
    *,
    name: str,
    panel: pd.DataFrame,
    selected: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    holding_sessions: int,
    cost: float,
    delay_sessions: int,
    selection_sha256: str,
) -> ScenarioResult:
    empty = pd.Series(0.0, index=calendar, dtype=float, name=name)
    if selected.empty:
        return ScenarioResult(name, empty, False, "NO_COMPLETE_COHORTS", 0, selection_sha256)
    session_ordinals = {session: ordinal for ordinal, session in enumerate(calendar)}
    price_lookup = panel.set_index(["symbol", "session_date"])[["open", "close"]]
    daily_contributions: dict[pd.Timestamp, list[float]] = {}
    cohorts = 0
    for signal_date, cohort in selected.groupby("signal_date", sort=True, observed=True):
        signal_ordinal = session_ordinals[pd.Timestamp(signal_date)]
        entry_ordinal = signal_ordinal + 1 + delay_sessions
        exit_ordinal = entry_ordinal + holding_sessions
        if exit_ordinal >= len(calendar):
            raise AssertionError("FULL_MARKET_DAILY_SELECTION_HORIZON_INVALID")
        path_dates = calendar[entry_ordinal : exit_ordinal + 1]
        cohort_daily: dict[pd.Timestamp, list[float]] = {
            session: [] for session in path_dates
        }
        for symbol in cohort["symbol"]:
            keys = [(symbol, session) for session in path_dates]
            if any(key not in price_lookup.index for key in keys):
                return ScenarioResult(
                    name,
                    empty,
                    False,
                    "SELECTED_PATH_MISSING",
                    cohorts,
                    selection_sha256,
                )
            prices = price_lookup.loc[keys]
            if len(prices) != len(path_dates):
                return ScenarioResult(
                    name,
                    empty,
                    False,
                    "SELECTED_PATH_MISSING",
                    cohorts,
                    selection_sha256,
                )
            entry_return = float(prices.iloc[0]["close"] / prices.iloc[0]["open"] - 1.0 - cost)
            cohort_daily[path_dates[0]].append(entry_return)
            for offset in range(1, holding_sessions):
                holding_return = float(
                    prices.iloc[offset]["close"] / prices.iloc[offset - 1]["close"] - 1.0
                )
                cohort_daily[path_dates[offset]].append(holding_return)
            exit_return = float(
                prices.iloc[-1]["open"] / prices.iloc[-2]["close"] - 1.0
            )
            cohort_daily[path_dates[-1]].append(exit_return)
        for session, symbol_returns in cohort_daily.items():
            daily_contributions.setdefault(session, []).append(float(np.mean(symbol_returns)))
        cohorts += 1
    daily = empty.copy()
    for session, cohort_returns in daily_contributions.items():
        daily.loc[session] = float(np.mean(cohort_returns))
    return ScenarioResult(name, daily, True, None, cohorts, selection_sha256)


def evaluate_scenarios(
    panel: pd.DataFrame, spec: Specification
) -> dict[str, ScenarioResult]:
    """Evaluate fixed selections under standard, cost, and delay scenarios."""
    required = {"symbol", "session_date", "open", "close", *FAMILIES}
    missing = required.difference(panel.columns)
    if missing:
        raise ValueError(f"FULL_MARKET_DAILY_PORTFOLIO_SCHEMA_MISSING:{sorted(missing)}")
    frame = panel.loc[:, sorted(required)].copy()
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame["session_date"] = pd.to_datetime(
        frame["session_date"], errors="raise"
    ).dt.normalize()
    if frame[["symbol", "session_date"]].duplicated().any():
        raise ValueError("FULL_MARKET_DAILY_PORTFOLIO_KEY_DUPLICATE")
    for column in ("open", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if (
        not np.isfinite(frame[["open", "close"]]).all(axis=1).all()
        or not frame[["open", "close"]].gt(0).all(axis=1).all()
    ):
        raise ValueError("FULL_MARKET_DAILY_PORTFOLIO_PRICE_INVALID")
    if spec.family not in FAMILIES:
        raise ValueError(f"FULL_MARKET_DAILY_UNKNOWN_FAMILY:{spec.family}")
    calendar = pd.DatetimeIndex(sorted(frame["session_date"].unique()))
    selected = _selection_rows(frame, spec, calendar)
    selection_sha256 = _selection_sha256(selected)
    definitions = (
        ("standard_9bp", 0.0009, 0),
        ("cost_18bp", 0.0018, 0),
        ("delay_1session_9bp", 0.0009, 1),
    )
    return {
        name: _scenario_result(
            name=name,
            panel=frame,
            selected=selected,
            calendar=calendar,
            holding_sessions=spec.holding_sessions,
            cost=cost,
            delay_sessions=delay,
            selection_sha256=selection_sha256,
        )
        for name, cost, delay in definitions
    }


def performance_metrics(daily_returns: pd.Series) -> dict[str, float | int]:
    """Calculate frozen discovery metrics without dropping any session."""
    returns = pd.to_numeric(daily_returns, errors="coerce")
    if returns.empty or not np.isfinite(returns).all() or returns.le(-1.0).any():
        raise ValueError("FULL_MARKET_DAILY_RETURNS_INVALID")
    count = len(returns)
    log_total = float(np.log1p(returns).sum())
    annualized_return = float(np.exp(log_total * 252.0 / count) - 1.0)
    wealth = np.exp(np.log1p(returns).cumsum())
    max_drawdown = float(-(wealth / wealth.cummax() - 1.0).min())
    standard_deviation = float(returns.std(ddof=1))
    if standard_deviation <= 0:
        information_ratio = 0.0
        z_score = 0.0
    else:
        information_ratio = float(returns.mean() / standard_deviation * np.sqrt(252.0))
        z_score = float(returns.mean() / standard_deviation * np.sqrt(count))
    folds = np.array_split(returns.to_numpy(dtype=float), 5)
    positive_folds = sum(float(np.prod(1.0 + fold) - 1.0) > 0 for fold in folds)
    return {
        "annualized_return": annualized_return,
        "max_drawdown": max_drawdown,
        "information_ratio": information_ratio,
        "z_score": z_score,
        "positive_folds": positive_folds,
        "observations": count,
    }


def passes_basic_pre_null_gates(
    metrics_by_scenario: dict[str, dict[str, float | int]],
) -> bool:
    """Apply the unchanged economic, cost, delay, fold, and z gates."""
    required = {"standard_9bp", "cost_18bp", "delay_1session_9bp"}
    if set(metrics_by_scenario) != required:
        raise ValueError("FULL_MARKET_DAILY_SCENARIO_SET_INVALID")
    for metrics in metrics_by_scenario.values():
        if not (
            float(metrics["annualized_return"]) > 0.40
            and float(metrics["max_drawdown"]) < 0.20
            and float(metrics["information_ratio"]) >= 1.0
            and float(metrics["z_score"]) >= 3.0
            and int(metrics["positive_folds"]) >= 4
        ):
            return False
    return True
