"""Frozen full-market daily overnight/intraday decomposition contract."""

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
    "persistent_overnight_drift",
    "overnight_underreaction",
    "persistent_intraday_drift",
    "gap_reversal_quality",
    "session_divergence",
)
LOOKBACKS = (20, 42, 63, 126)
REFRESH_LIFE_PAIRS = ((1, 1), (5, 5), (5, 10), (10, 10), (21, 21))
TOP_COUNTS = (10, 20, 40, 80)

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


@dataclass(frozen=True, slots=True)
class Specification:
    family: str
    lookback: int
    refresh_sessions: int
    life_sessions: int
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
                raise ValueError(f"FULL_MARKET_SESSION_IDENTITY_HASH_INVALID:{name}")

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
            raise ValueError("FULL_MARKET_SESSION_CHECKPOINT_TOTAL_INVALID")
        if path.exists():
            state = json.loads(path.read_text("utf-8"))
            if (
                state.get("identity") != asdict(identity)
                or state.get("identity_sha256") != identity.sha256
                or state.get("total_cells") != total_cells
            ):
                raise RuntimeError("FULL_MARKET_SESSION_CHECKPOINT_IDENTITY_MISMATCH")
            cells_completed = state.get("cells_completed")
            chain_sha256 = state.get("chain_sha256")
            if (
                not isinstance(cells_completed, int)
                or not 0 <= cells_completed <= total_cells
                or not isinstance(chain_sha256, str)
                or re.fullmatch(r"[0-9a-f]{64}", chain_sha256) is None
            ):
                raise RuntimeError("FULL_MARKET_SESSION_CHECKPOINT_STATE_INVALID")
            return cls(path, identity, total_cells, cells_completed, chain_sha256)
        checkpoint = cls(
            path, identity, total_cells, 0, hashlib.sha256(b"").hexdigest()
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
        temporary.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n", "utf-8"
        )
        os.replace(temporary, self.path)

    def record_cell(self, cell_index: int, result_sha256: str) -> None:
        if cell_index != self.cells_completed or cell_index >= self.total_cells:
            raise RuntimeError("FULL_MARKET_SESSION_CHECKPOINT_CELL_ORDER_INVALID")
        if re.fullmatch(r"[0-9a-f]{64}", result_sha256) is None:
            raise ValueError("FULL_MARKET_SESSION_CHECKPOINT_RESULT_HASH_INVALID")
        self.chain_sha256 = _advance_chain(
            self.chain_sha256, cell_index, result_sha256
        )
        self.cells_completed += 1
        self._write()


def specifications() -> tuple[Specification, ...]:
    """Return the immutable 400-cell session-decomposition grid."""
    result = tuple(
        Specification(family, lookback, refresh, life, top_count)
        for family in FAMILIES
        for lookback in LOOKBACKS
        for refresh, life in REFRESH_LIFE_PAIRS
        for top_count in TOP_COUNTS
    )
    if len(result) != 400 or len(set(result)) != 400:
        raise AssertionError("FULL_MARKET_SESSION_GRID_INVALID")
    return result


def _validate_daily_bars(daily_bars: pd.DataFrame) -> pd.DataFrame:
    missing = _DAILY_COLUMNS.difference(daily_bars.columns)
    if missing:
        raise ValueError(f"SESSION_DAILY_SCHEMA_MISSING:{sorted(missing)}")
    forbidden_tokens = (
        "headline",
        "news",
        "event",
        "filing",
        "sec_",
        "fundamental",
        "issuer",
        "announcement",
    )
    forbidden = sorted(
        column
        for column in daily_bars.columns
        if column not in _DAILY_COLUMNS
        and any(token in column.lower() for token in forbidden_tokens)
    )
    if forbidden:
        raise ValueError(f"FORBIDDEN_INPUT_COLUMN:{forbidden}")
    result = daily_bars.loc[:, sorted(_DAILY_COLUMNS)].copy()
    result["symbol"] = result["symbol"].astype(str).str.upper()
    result["session_date"] = pd.to_datetime(result["session_date"], errors="raise")
    if result.duplicated(["symbol", "session_date"]).any():
        raise ValueError("SESSION_DAILY_KEY_DUPLICATE")
    numeric = ["open", "high", "low", "close", "volume", "vwap", "trade_count"]
    result[numeric] = result[numeric].apply(pd.to_numeric, errors="coerce")
    sentinel = (
        result["volume"].eq(0)
        & result["trade_count"].eq(0)
        & result["vwap"].eq(0)
    )
    result.loc[sentinel, "vwap"] = np.nan
    prices_valid = result[["open", "high", "low", "close"]].gt(0).all(axis=1)
    flows_valid = result[["volume", "trade_count"]].ge(0).all(axis=1)
    vwap_valid = result["vwap"].gt(0) | result["vwap"].isna()
    finite_required = np.isfinite(
        result[["open", "high", "low", "close", "volume", "trade_count"]]
    ).all(axis=1)
    if not (prices_valid & flows_valid & vwap_valid & finite_required).all():
        raise ValueError("SESSION_DAILY_VALUES_INVALID")
    return result.sort_values(["symbol", "session_date"], kind="stable").reset_index(
        drop=True
    )


def build_session_features(daily_bars: pd.DataFrame) -> pd.DataFrame:
    """Build atomic close-to-open and open-to-close features causally."""
    result = _validate_daily_bars(daily_bars)
    grouped = result.groupby("symbol", sort=False, observed=True)
    prior_close = grouped["close"].shift(1)
    result["overnight_log_return"] = np.log(result["open"] / prior_close)
    result["intraday_log_return"] = np.log(result["close"] / result["open"])
    result["close_above_vwap"] = np.where(
        result["vwap"].notna(), result["close"].gt(result["vwap"]).astype(float), np.nan
    )
    result["dollar_volume"] = result["close"] * result["volume"]
    return result


def _rolling(
    frame: pd.DataFrame,
    column: str,
    lookback: int,
    operation: str,
) -> pd.Series:
    grouped = frame.groupby("symbol", sort=False, observed=True)[column]
    if operation == "sum":
        return grouped.transform(
            lambda values: values.rolling(lookback, min_periods=lookback).sum()
        )
    if operation == "mean":
        return grouped.transform(
            lambda values: values.rolling(lookback, min_periods=lookback).mean()
        )
    if operation == "std":
        return grouped.transform(
            lambda values: values.rolling(lookback, min_periods=lookback).std(ddof=1)
        )
    raise ValueError(f"SESSION_ROLLING_OPERATION_INVALID:{operation}")


def _session_rank(frame: pd.DataFrame, values: pd.Series) -> pd.Series:
    ranked = pd.Series(np.nan, index=frame.index, dtype=float)
    for positions in frame.groupby(
        "session_date", sort=False, observed=True
    ).groups.values():
        positions = list(positions)
        session_values = values.loc[positions]
        finite = session_values[np.isfinite(session_values)]
        if finite.empty:
            continue
        lower = finite.quantile(0.01)
        upper = finite.quantile(0.99)
        ordered = frame.loc[finite.index, "symbol"].sort_values(kind="stable").index
        clipped = session_values.loc[ordered].clip(lower=lower, upper=upper)
        ranked.loc[ordered] = clipped.rank(method="first", pct=True).to_numpy()
    return ranked


def score_session_families(features: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Score the five frozen session-decomposition families."""
    if lookback not in LOOKBACKS:
        raise ValueError("SESSION_LOOKBACK_INVALID")
    frame = features.sort_values(["symbol", "session_date"], kind="stable").reset_index(
        drop=True
    )
    overnight_sum = _rolling(frame, "overnight_log_return", lookback, "sum")
    intraday_sum = _rolling(frame, "intraday_log_return", lookback, "sum")
    overnight_hit = _rolling(
        frame.assign(_overnight_hit=frame["overnight_log_return"].gt(0).astype(float)),
        "_overnight_hit",
        lookback,
        "mean",
    )
    intraday_hit = _rolling(
        frame.assign(_intraday_hit=frame["intraday_log_return"].gt(0).astype(float)),
        "_intraday_hit",
        lookback,
        "mean",
    )
    overnight_vol = _rolling(frame, "overnight_log_return", lookback, "std")
    intraday_vol = _rolling(frame, "intraday_log_return", lookback, "std")
    dollar_volume = _rolling(frame, "dollar_volume", lookback, "mean")
    vwap_frequency = _rolling(frame, "close_above_vwap", lookback, "mean")

    ranks = {
        "overnight_sum": _session_rank(frame, overnight_sum),
        "intraday_sum": _session_rank(frame, intraday_sum),
        "overnight_hit": _session_rank(frame, overnight_hit),
        "intraday_hit": _session_rank(frame, intraday_hit),
        "overnight_vol": _session_rank(frame, overnight_vol),
        "intraday_vol": _session_rank(frame, intraday_vol),
        "dollar_volume": _session_rank(frame, dollar_volume),
        "gap_reversal": _session_rank(frame, -frame["overnight_log_return"]),
        "divergence": _session_rank(frame, overnight_sum - intraday_sum),
        "vwap_frequency": _session_rank(frame, vwap_frequency),
    }
    result = frame.loc[:, ["symbol", "session_date"]].copy()
    result["persistent_overnight_drift"] = (
        ranks["overnight_sum"] + ranks["overnight_hit"] + (1.0 - ranks["overnight_vol"])
    ) / 3.0
    result["overnight_underreaction"] = (
        ranks["overnight_sum"] + (1.0 - ranks["intraday_sum"]) + ranks["dollar_volume"]
    ) / 3.0
    result["persistent_intraday_drift"] = (
        ranks["intraday_sum"] + ranks["intraday_hit"] + (1.0 - ranks["intraday_vol"])
    ) / 3.0
    result["gap_reversal_quality"] = (
        ranks["gap_reversal"] + ranks["intraday_sum"] + (1.0 - ranks["overnight_vol"])
    ) / 3.0
    result["session_divergence"] = (
        ranks["divergence"] + ranks["vwap_frequency"] + ranks["dollar_volume"]
    ) / 3.0
    return result


def _selection_rows(
    panel: pd.DataFrame,
    spec: Specification,
    calendar: pd.DatetimeIndex,
) -> pd.DataFrame:
    latest_signal_ordinal = len(calendar) - spec.life_sessions - 2
    if latest_signal_ordinal < 0:
        return pd.DataFrame(columns=["signal_date", "symbol", "selection_rank"])
    signal_dates = set(calendar[: latest_signal_ordinal + 1 : spec.refresh_sessions])
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
    counts = candidates.groupby("session_date", observed=True)["symbol"].transform(
        "size"
    )
    selected = candidates.loc[
        counts.ge(spec.top_count) & candidates["selection_rank"].le(spec.top_count)
    ].rename(columns={"session_date": "signal_date"})
    return selected.loc[:, ["signal_date", "symbol", "selection_rank"]].reset_index(
        drop=True
    )


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
    spec: Specification,
    cost: float,
    delay_sessions: int,
    selection_sha256: str,
) -> ScenarioResult:
    empty = pd.Series(0.0, index=calendar, dtype=float, name=name)
    if selected.empty:
        return ScenarioResult(
            name, empty, False, "NO_COMPLETE_COHORTS", 0, selection_sha256
        )
    overnight_family = spec.family in {
        "persistent_overnight_drift",
        "overnight_underreaction",
        "session_divergence",
    }
    session_ordinals = {session: ordinal for ordinal, session in enumerate(calendar)}
    price_lookup = panel.set_index(["symbol", "session_date"])[
        ["open", "close", "volume", "trade_count"]
    ]
    daily_contributions: dict[pd.Timestamp, list[float]] = {}
    cohorts = 0
    for signal_date, cohort in selected.groupby(
        "signal_date", sort=True, observed=True
    ):
        signal_ordinal = session_ordinals[pd.Timestamp(signal_date)]
        entry_ordinal = signal_ordinal + 1 + delay_sessions
        end_ordinal = entry_ordinal + spec.life_sessions
        if end_ordinal > len(calendar):
            raise AssertionError("FULL_MARKET_SESSION_SELECTION_HORIZON_INVALID")
        exposure_dates = calendar[entry_ordinal:end_ordinal]
        cohort_daily = {session: [] for session in exposure_dates}
        for symbol in cohort["symbol"]:
            for exposure_date in exposure_dates:
                exposure_ordinal = session_ordinals[exposure_date]
                exposure_key = (symbol, exposure_date)
                if exposure_key not in price_lookup.index:
                    return ScenarioResult(
                        name,
                        empty,
                        False,
                        "SELECTED_EXPOSURE_MISSING",
                        cohorts,
                        selection_sha256,
                    )
                exposure = price_lookup.loc[exposure_key]
                if exposure[["volume", "trade_count"]].le(0).any():
                    return ScenarioResult(
                        name,
                        empty,
                        False,
                        "SELECTED_EXPOSURE_ZERO_LIQUIDITY",
                        cohorts,
                        selection_sha256,
                    )
                if overnight_family:
                    prior_date = calendar[exposure_ordinal - 1]
                    prior_key = (symbol, prior_date)
                    if prior_key not in price_lookup.index:
                        return ScenarioResult(
                            name,
                            empty,
                            False,
                            "SELECTED_EXPOSURE_MISSING",
                            cohorts,
                            selection_sha256,
                        )
                    leg_return = float(
                        exposure["open"] / price_lookup.loc[prior_key]["close"]
                        - 1.0
                        - cost
                    )
                else:
                    leg_return = float(exposure["close"] / exposure["open"] - 1.0 - cost)
                cohort_daily[exposure_date].append(leg_return)
        for session, symbol_returns in cohort_daily.items():
            daily_contributions.setdefault(session, []).append(
                float(np.mean(symbol_returns))
            )
        cohorts += 1
    daily = empty.copy()
    for session, cohort_returns in daily_contributions.items():
        daily.loc[session] = float(np.mean(cohort_returns))
    return ScenarioResult(name, daily, True, None, cohorts, selection_sha256)


def evaluate_session_scenarios(
    panel: pd.DataFrame,
    spec: Specification,
) -> dict[str, ScenarioResult]:
    """Evaluate fixed selections under session-specific exposure legs."""
    required = {
        "symbol",
        "session_date",
        "open",
        "close",
        "volume",
        "trade_count",
        *FAMILIES,
    }
    missing = required.difference(panel.columns)
    if missing:
        raise ValueError(f"SESSION_PORTFOLIO_SCHEMA_MISSING:{sorted(missing)}")
    if spec not in specifications():
        raise ValueError("SESSION_SPECIFICATION_NOT_FROZEN")
    frame = panel.loc[:, sorted(required)].copy()
    frame["symbol"] = frame["symbol"].astype(str).str.upper()
    frame["session_date"] = pd.to_datetime(frame["session_date"], errors="raise")
    if frame.duplicated(["symbol", "session_date"]).any():
        raise ValueError("SESSION_PORTFOLIO_KEY_DUPLICATE")
    numeric = ["open", "close", "volume", "trade_count"]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
    if (
        not np.isfinite(frame[numeric]).all(axis=1).all()
        or not frame[["open", "close"]].gt(0).all(axis=1).all()
        or not frame[["volume", "trade_count"]].ge(0).all(axis=1).all()
    ):
        raise ValueError("SESSION_PORTFOLIO_PRICE_INVALID")
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
            spec=spec,
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
        raise ValueError("FULL_MARKET_SESSION_RETURNS_INVALID")
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
        information_ratio = float(
            returns.mean() / standard_deviation * np.sqrt(252.0)
        )
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
    """Apply unchanged economic, cost, delay, fold, and z gates."""
    required = {"standard_9bp", "cost_18bp", "delay_1session_9bp"}
    if set(metrics_by_scenario) != required:
        raise ValueError("FULL_MARKET_SESSION_SCENARIO_SET_INVALID")
    return all(
        float(metrics["annualized_return"]) > 0.40
        and float(metrics["max_drawdown"]) < 0.20
        and float(metrics["information_ratio"]) >= 1.0
        and float(metrics["z_score"]) >= 3.0
        and int(metrics["positive_folds"]) >= 4
        for metrics in metrics_by_scenario.values()
    )


def _canonical_json_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _advance_chain(chain_sha256: str, cell_index: int, result_sha256: str) -> str:
    digest = hashlib.sha256()
    digest.update(bytes.fromhex(chain_sha256))
    digest.update(cell_index.to_bytes(8, byteorder="big", signed=False))
    digest.update(bytes.fromhex(result_sha256))
    return digest.hexdigest()


def evaluate_cell_record(
    panel: pd.DataFrame, spec: Specification, *, cell_index: int
) -> dict[str, object]:
    """Evaluate one consumed-period cell without promotion side effects."""
    scenarios = evaluate_session_scenarios(panel, spec)
    valid = all(result.valid for result in scenarios.values())
    metrics_by_scenario: dict[str, dict[str, float | int]] = {}
    if valid:
        metrics_by_scenario = {
            name: performance_metrics(result.daily_returns)
            for name, result in scenarios.items()
        }
    return {
        "cell_index": cell_index,
        "specification": asdict(spec),
        "valid": valid,
        "invalid_reasons": {
            name: result.invalid_reason
            for name, result in scenarios.items()
            if result.invalid_reason is not None
        },
        "selection_sha256": {
            name: result.selection_sha256 for name, result in scenarios.items()
        },
        "cohorts": {name: result.cohorts for name, result in scenarios.items()},
        "metrics": metrics_by_scenario,
        "basic_pre_null_passed": (
            passes_basic_pre_null_gates(metrics_by_scenario) if valid else False
        ),
        "consumed_period": True,
        "independent_oos": False,
        "paper_activation": False,
        "order_route": "FORBIDDEN",
    }


def evaluate_cells_sequential(
    panel: pd.DataFrame,
    specs: tuple[Specification, ...],
    checkpoint: AtomicCheckpoint,
    cell_directory: Path,
) -> list[dict[str, object]]:
    """Evaluate cells in order and persist each before checkpoint advance."""
    if len(specs) != checkpoint.total_cells:
        raise RuntimeError("FULL_MARKET_SESSION_CHECKPOINT_GRID_SIZE_MISMATCH")
    cell_directory.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    reconstructed_chain = hashlib.sha256(b"").hexdigest()
    for cell_index in range(checkpoint.cells_completed):
        path = cell_directory / f"cell-{cell_index:04d}.json"
        if not path.exists():
            raise RuntimeError("FULL_MARKET_SESSION_COMPLETED_CELL_MISSING")
        record = json.loads(path.read_text("utf-8"))
        if record.get("cell_index") != cell_index:
            raise RuntimeError("FULL_MARKET_SESSION_COMPLETED_CELL_INDEX_INVALID")
        result_sha256 = _canonical_json_sha256(record)
        reconstructed_chain = _advance_chain(
            reconstructed_chain, cell_index, result_sha256
        )
        records.append(record)
    if reconstructed_chain != checkpoint.chain_sha256:
        raise RuntimeError("FULL_MARKET_SESSION_CHECKPOINT_CHAIN_MISMATCH")
    for cell_index in range(checkpoint.cells_completed, len(specs)):
        record = evaluate_cell_record(panel, specs[cell_index], cell_index=cell_index)
        result_sha256 = _canonical_json_sha256(record)
        path = cell_directory / f"cell-{cell_index:04d}.json"
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n", "utf-8"
        )
        os.replace(temporary, path)
        checkpoint.record_cell(cell_index, result_sha256)
        records.append(record)
    return records
