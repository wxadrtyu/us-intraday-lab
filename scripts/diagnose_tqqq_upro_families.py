"""Development-only causal scan of TQQQ/UPRO pair mechanisms."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from us_intraday_lab.long_horizon.hf_snapshot import HfFiveMinuteSnapshotStore
from us_intraday_lab.long_horizon.splits import create_long_horizon_split

ROOT = Path(r"G:\us-intraday-lab")
DATASET_ID = "hf-finnhub-5min-4612a96827c4daa416e359fe51cb8c8f"
SYMBOLS = ("TQQQ", "UPRO")
ROUND_TRIP_COST_1_5X = 0.0009


@dataclass(frozen=True)
class Result:
    family: str
    parameters: tuple[object, ...]
    train_annual: float
    validation_annual: float
    validation_ir: float
    validation_legacy_close_to_close_ir: float
    validation_drawdown: float
    validation_profit_factor: float
    validation_trades: int
    validation_concentration: float
    folds: tuple[float, ...]


def metrics(returns: pd.Series) -> tuple[float, float, float]:
    equity = (1.0 + returns).cumprod()
    annual = float(equity.iloc[-1] ** (252.0 / len(returns)) - 1.0)
    drawdown = float((equity / equity.cummax() - 1.0).min())
    gains = float(returns.clip(lower=0.0).sum())
    losses = abs(float(returns.clip(upper=0.0).sum()))
    return annual, drawdown, gains / losses if losses else math.inf


def information_ratio(returns: pd.Series, benchmark: pd.Series) -> float:
    active = returns - benchmark
    deviation = float(active.std(ddof=1))
    return float(active.mean() / deviation * math.sqrt(252.0)) if deviation else -math.inf


def main() -> None:
    store = HfFiveMinuteSnapshotStore(root=ROOT, dataset_id=DATASET_ID)
    split = create_long_horizon_split(store.accepted_sessions, split_id="diagnostic")
    sessions = split.train_sessions + split.validation_sessions
    dates = pd.Index(sessions, name="session_date")
    train_mask = pd.Series(dates.isin(split.train_sessions), index=dates)
    bars = store.read_sessions(sessions).sort_values(
        ["symbol", "session_date", "timestamp"], kind="stable"
    )
    groups = bars.groupby(["symbol", "session_date"], observed=True, sort=True)
    bars["bar_index"] = groups.cumcount()
    day_open = groups["open"].first().unstack("symbol").reindex(dates)
    day_close = groups["close"].last().unstack("symbol").reindex(dates)
    prior_return = day_close.pct_change(fill_method=None).shift(1)
    trail3 = day_close.pct_change(3, fill_method=None).shift(1)
    trail5 = day_close.pct_change(5, fill_method=None).shift(1)
    indexes = sorted(
        {minute // 5 - 1 for minute in (30, 60, 90, 120, 150, 180, 240)}
        | {minute // 5 for minute in (30, 60, 90, 120, 150, 180, 240, 300, 330)}
    )
    wanted = bars.loc[bars["bar_index"].isin(indexes)]
    closes = wanted.pivot_table(
        index="session_date", columns=["bar_index", "symbol"], values="close"
    ).reindex(dates)
    opens = wanted.pivot_table(
        index="session_date", columns=["bar_index", "symbol"], values="open"
    ).reindex(dates)
    benchmark = day_close["UPRO"].pct_change(fill_method=None).fillna(0.0)
    scanned: list[Result] = []
    passing: list[Result] = []

    def evaluate(
        family: str,
        parameters: tuple[object, ...],
        positions: pd.DataFrame,
        raw: pd.DataFrame,
    ) -> None:
        positions = positions.reindex(index=dates, columns=SYMBOLS).fillna(0.0)
        components = positions * (raw - ROUND_TRIP_COST_1_5X)
        returns = components.sum(axis=1).fillna(0.0)
        matched_benchmark = positions.sum(axis=1) * (raw["UPRO"] - ROUND_TRIP_COST_1_5X)
        train_values = metrics(returns.loc[train_mask])
        validation = returns.loc[~train_mask]
        validation_values = metrics(validation)
        boundaries = np.linspace(0, len(validation), 5, dtype=int)
        folds = tuple(
            metrics(validation.iloc[boundaries[i] : boundaries[i + 1]])[0] for i in range(4)
        )
        pnl = components.loc[~train_mask].sum().clip(lower=0.0)
        concentration = float(pnl.max() / pnl.sum()) if float(pnl.sum()) > 0.0 else 1.0
        result = Result(
            family=family,
            parameters=parameters,
            train_annual=train_values[0],
            validation_annual=validation_values[0],
            validation_ir=information_ratio(
                validation, matched_benchmark.loc[~train_mask].fillna(0.0)
            ),
            validation_legacy_close_to_close_ir=information_ratio(
                validation, benchmark.loc[~train_mask]
            ),
            validation_drawdown=validation_values[1],
            validation_profit_factor=validation_values[2],
            validation_trades=int((positions.loc[~train_mask] > 0.0).sum().sum()),
            validation_concentration=concentration,
            folds=folds,
        )
        scanned.append(result)
        if (
            result.train_annual >= 0.08
            and result.validation_annual >= 0.10
            and result.validation_ir >= 0.50
            and result.validation_drawdown >= -0.08
            and result.validation_profit_factor >= 1.15
            and result.validation_trades >= 100
            and result.validation_concentration <= 0.70
            and sum(value > 0.0 for value in folds) >= 3
        ):
            passing.append(result)

    for decision in (30, 60, 90, 120, 150, 180, 240):
        signal_close = closes[decision // 5 - 1].reindex(columns=SYMBOLS)
        current = signal_close / day_open - 1.0
        relative = current["TQQQ"] - current["UPRO"]
        for exit_minute in (120, 180, 240, 300, 330):
            if exit_minute <= decision:
                continue
            entry = opens[decision // 5].reindex(columns=SYMBOLS)
            exit_prices = opens[exit_minute // 5].reindex(columns=SYMBOLS)
            raw = exit_prices / entry - 1.0
            for gap in (0.0025, 0.004, 0.006, 0.009, 0.012, 0.018):
                for floor in (-0.03, -0.02, -0.01, 0.0):
                    upro_lag = (relative >= gap) & (current["UPRO"] >= floor)
                    tqqq_lag = (relative <= -gap) & (current["TQQQ"] >= floor)
                    positions = pd.DataFrame(0.0, index=dates, columns=SYMBOLS)
                    positions.loc[upro_lag, "UPRO"] = 0.49
                    positions.loc[tqqq_lag, "TQQQ"] = 0.49
                    evaluate(
                        "relative_laggard",
                        (decision, exit_minute, gap, floor),
                        positions,
                        raw,
                    )
            for crash in (-0.03, -0.05, -0.075, -0.10, -0.15):
                for recovery in (0.0, 0.0015, 0.003, 0.005, 0.008):
                    signal = (
                        (trail5["TQQQ"] <= crash)
                        & (trail5["UPRO"] <= crash * 0.6)
                        & (current.min(axis=1) >= recovery)
                    )
                    positions = pd.DataFrame(
                        np.repeat(signal.to_numpy()[:, None], 2, axis=1) * 0.375,
                        index=dates,
                        columns=SYMBOLS,
                    )
                    evaluate(
                        "five_day_recovery",
                        (decision, exit_minute, crash, recovery),
                        positions,
                        raw,
                    )
            for prior_ceiling in (-0.005, -0.01, -0.015, -0.025, -0.04):
                for recovery in (0.0, 0.0015, 0.003, 0.005):
                    signal = (
                        (prior_return.max(axis=1) <= prior_ceiling)
                        & (current.min(axis=1) >= recovery)
                        & (trail3.min(axis=1) >= -0.15)
                    )
                    positions = pd.DataFrame(
                        np.repeat(signal.to_numpy()[:, None], 2, axis=1) * 0.375,
                        index=dates,
                        columns=SYMBOLS,
                    )
                    evaluate(
                        "prior_day_reversal",
                        (decision, exit_minute, prior_ceiling, recovery),
                        positions,
                        raw,
                    )

    decision = 30
    signal_close = closes[decision // 5 - 1].reindex(columns=SYMBOLS)
    current = signal_close / day_open - 1.0
    relative = current["TQQQ"] - current["UPRO"]
    entry = opens[decision // 5].reindex(columns=SYMBOLS)
    for exit_minute in (300, 330):
        exit_prices = opens[exit_minute // 5].reindex(columns=SYMBOLS)
        raw = exit_prices / entry - 1.0
        for gap in (0.0025, 0.004, 0.006):
            for floor in (-0.02, -0.01, 0.0):
                laggard = pd.DataFrame(0.0, index=dates, columns=SYMBOLS)
                laggard.loc[(relative >= gap) & (current["UPRO"] >= floor), "UPRO"] = 1.0
                laggard.loc[(relative <= -gap) & (current["TQQQ"] >= floor), "TQQQ"] = 1.0
                for prior_ceiling in (-0.01, -0.015, -0.025):
                    for recovery in (0.0, 0.0015, 0.003, 0.005):
                        recovery_signal = (
                            (prior_return.max(axis=1) <= prior_ceiling)
                            & (current.min(axis=1) >= recovery)
                            & (trail3.min(axis=1) >= -0.15)
                        )
                        recovery_positions = pd.DataFrame(
                            np.repeat(recovery_signal.to_numpy()[:, None], 2, axis=1),
                            index=dates,
                            columns=SYMBOLS,
                        )
                        for laggard_weight, recovery_weight in (
                            (0.49, 0.25),
                            (0.40, 0.35),
                            (0.35, 0.40),
                            (0.49, 0.49),
                        ):
                            positions = (
                                laggard * laggard_weight
                                + recovery_positions * (recovery_weight / 2.0)
                            ).clip(upper=0.49)
                            evaluate(
                                "laggard_plus_prior_recovery",
                                (
                                    exit_minute,
                                    gap,
                                    floor,
                                    prior_ceiling,
                                    recovery,
                                    laggard_weight,
                                    recovery_weight,
                                ),
                                positions,
                                raw,
                            )

    # Combine two distinct, symbol-specific mechanisms.  TQQQ supplies the
    # short-horizon crash-rebound branch that previously diversified the SOXL
    # laggard strategy; UPRO supplies the cleaner positive-session laggard
    # branch found above.  Each branch remains capped at 49% cash and uses only
    # information available before its own fixed entry.
    for tqqq_entry_minute in (60, 90, 120):
        tqqq_entry = opens[tqqq_entry_minute // 5].reindex(columns=SYMBOLS)
        for tqqq_exit_minute in (150, 180, 240):
            if tqqq_exit_minute <= tqqq_entry_minute:
                continue
            tqqq_exit = opens[tqqq_exit_minute // 5].reindex(columns=SYMBOLS)
            tqqq_raw = tqqq_exit / tqqq_entry - 1.0
            for crash in (-0.075, -0.10, -0.125, -0.15):
                tqqq_signal = trail3["TQQQ"] <= crash
                for upro_entry_minute in (30, 60):
                    upro_signal_close = closes[upro_entry_minute // 5 - 1].reindex(columns=SYMBOLS)
                    upro_current = upro_signal_close / day_open - 1.0
                    upro_relative = upro_current["TQQQ"] - upro_current["UPRO"]
                    upro_entry = opens[upro_entry_minute // 5].reindex(columns=SYMBOLS)
                    for upro_exit_minute in (300, 330):
                        upro_exit = opens[upro_exit_minute // 5].reindex(columns=SYMBOLS)
                        upro_raw = upro_exit / upro_entry - 1.0
                        raw = pd.DataFrame(0.0, index=dates, columns=SYMBOLS)
                        raw["TQQQ"] = tqqq_raw["TQQQ"]
                        raw["UPRO"] = upro_raw["UPRO"]
                        for gap in (0.0025, 0.004, 0.006):
                            for floor in (0.0, 0.002):
                                for prior_floor in (-0.10, -0.05, -0.03):
                                    upro_signal = (
                                        (upro_relative >= gap)
                                        & (upro_current["UPRO"] >= floor)
                                        & (prior_return.min(axis=1) >= prior_floor)
                                    )
                                    positions = pd.DataFrame(0.0, index=dates, columns=SYMBOLS)
                                    positions.loc[tqqq_signal, "TQQQ"] = 0.49
                                    positions.loc[upro_signal, "UPRO"] = 0.49
                                    evaluate(
                                        "asymmetric_crash_laggard",
                                        (
                                            tqqq_entry_minute,
                                            tqqq_exit_minute,
                                            crash,
                                            upro_entry_minute,
                                            upro_exit_minute,
                                            gap,
                                            floor,
                                            prior_floor,
                                        ),
                                        positions,
                                        raw,
                                    )

    print(
        json.dumps(
            {
                "scanned": len(scanned),
                "passing": len(passing),
                "gate_counts": {
                    "train_annual": sum(item.train_annual >= 0.08 for item in scanned),
                    "validation_annual": sum(item.validation_annual >= 0.10 for item in scanned),
                    "information_ratio": sum(item.validation_ir >= 0.50 for item in scanned),
                    "trades": sum(item.validation_trades >= 100 for item in scanned),
                    "folds": sum(sum(value > 0.0 for value in item.folds) >= 3 for item in scanned),
                },
            },
            sort_keys=True,
        )
    )
    for frontier, items in (
        (
            "passing",
            sorted(
                passing,
                key=lambda item: min(item.train_annual, item.validation_annual),
                reverse=True,
            )[:30],
        ),
        (
            "balanced",
            sorted(
                scanned,
                key=lambda item: (
                    min(item.train_annual, item.validation_annual),
                    item.validation_ir,
                ),
                reverse=True,
            )[:30],
        ),
        (
            "asymmetric",
            sorted(
                (item for item in scanned if item.family == "asymmetric_crash_laggard"),
                key=lambda item: (
                    min(item.train_annual, item.validation_annual),
                    sum(value > 0.0 for value in item.folds),
                    item.validation_ir,
                ),
                reverse=True,
            )[:20],
        ),
    ):
        for item in items:
            print(json.dumps({"frontier": frontier, **asdict(item)}, sort_keys=True))


if __name__ == "__main__":
    main()
