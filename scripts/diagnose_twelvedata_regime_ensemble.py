"""Development-only scan of dynamically allocated long-only regime ensembles."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from diagnose_twelvedata_cross_section import (
    ROUND_TRIP_COST_1_5X,
    information_ratio,
    load_daily,
    metrics,
)


@dataclass(frozen=True)
class Branch:
    family: str
    parameters: tuple[object, ...]
    positions: pd.DataFrame
    components: pd.DataFrame
    returns: pd.Series
    benchmark: pd.Series


@dataclass(frozen=True)
class Result:
    families: tuple[str, str]
    parameters: tuple[tuple[object, ...], tuple[object, ...], float]
    train_annual: float
    validation_annual: float
    validation_benchmark_annual: float
    validation_ir: float
    validation_drawdown: float
    validation_profit_factor: float
    validation_trades: int
    validation_concentration: float
    folds: tuple[float, ...]


def main() -> None:
    root = Path(os.environ.get("TWELVEDATA_ROOT", "E:/us-intraday-lab-data/twelvedata-http"))
    train, _train_benchmark = load_daily(root / "bars_1min/train.parquet", split="train")
    validation, _validation_benchmark = load_daily(
        root / "bars_1min/val.parquet", split="validation"
    )
    frame = pd.concat([train, validation], ignore_index=True)
    dates = pd.Index(sorted(frame["session_date"].unique()), name="session_date")
    train_dates = set(train["session_date"].unique())
    train_mask = pd.Series(dates.isin(train_dates), index=dates)
    symbols = tuple(sorted(frame["symbol"].unique()))

    def wide(column: str) -> pd.DataFrame:
        return frame.pivot(index="session_date", columns="symbol", values=column).reindex(
            index=dates, columns=symbols
        )

    day_open = wide("day_open")
    day_close = wide("day_close")
    trail3 = day_close.pct_change(3, fill_method=None).shift(1)
    close_at = {minute: wide(f"close_{minute}") for minute in (15, 30, 45, 60, 90, 120)}
    open_at = {
        minute: wide(f"open_{minute}")
        for minute in (16, 31, 46, 61, 91, 121, 150, 180, 240, 300, 330, 360)
    }
    vwap_at = {minute: wide(f"vwap_{minute}") for minute in (15, 30, 45, 60, 90, 120)}
    cumulative_volume_at = {
        minute: wide(f"cum_volume_{minute}") for minute in (15, 30, 45, 60, 90, 120)
    }
    range_high_at = {minute: wide(f"range_high_{minute}") for minute in (15, 30, 45, 60, 90, 120)}
    range_low_at = {minute: wide(f"range_low_{minute}") for minute in (15, 30, 45, 60, 90, 120)}
    spy_at = {
        minute: wide(f"spy_current_{minute}").median(axis=1)
        for minute in (15, 30, 45, 60, 90, 120, 150, 180, 240, 300, 330, 360)
    }

    branches: list[Branch] = []

    def add_branch(
        family: str,
        parameters: tuple[object, ...],
        selected: pd.DataFrame,
        raw: pd.DataFrame,
        *,
        decision: int,
        exit_minute: int,
    ) -> None:
        selected = selected.fillna(False)
        counts = selected.sum(axis=1).replace(0, np.nan)
        positions = selected.div(counts, axis=0).fillna(0.0)
        components = positions * (raw - ROUND_TRIP_COST_1_5X)
        active = positions.sum(axis=1)
        spy_raw = (1.0 + spy_at[exit_minute]) / (1.0 + spy_at[decision]) - 1.0
        branches.append(
            Branch(
                family=family,
                parameters=parameters,
                positions=positions,
                components=components,
                returns=components.sum(axis=1).fillna(0.0),
                benchmark=(active * spy_raw).fillna(0.0),
            )
        )

    for decision in (30, 45):
        current = close_at[decision] / day_open - 1.0
        relative_volume = cumulative_volume_at[decision] / (
            cumulative_volume_at[decision].shift(1).rolling(20, min_periods=10).median()
        )
        range_width = range_high_at[decision] - range_low_at[decision]
        range_position = (close_at[decision] - range_low_at[decision]) / range_width
        above_vwap = close_at[decision] >= vwap_at[decision]
        spy_up = spy_at[decision] > 0.0
        for exit_minute in (300, 330, 360):
            raw = open_at[exit_minute] / open_at[decision + 1] - 1.0
            for count in (3, 5):
                top = current.rank(axis=1, ascending=False, method="first") <= count
                for volume_floor in (1.5, 2.0):
                    for strength_floor in (0.005, 0.01):
                        for market_excess_floor in (0.0, 0.005, 0.01, 0.02):
                            market_excess = current.sub(spy_at[decision], axis=0)
                            add_branch(
                                "volume_strength",
                                (
                                    decision,
                                    exit_minute,
                                    count,
                                    volume_floor,
                                    strength_floor,
                                    market_excess_floor,
                                ),
                                top
                                & (current >= strength_floor)
                                & (market_excess >= market_excess_floor)
                                & (relative_volume >= volume_floor)
                                & above_vwap
                                & (range_position >= 0.80)
                                & spy_up.to_numpy()[:, None],
                                raw,
                                decision=decision,
                                exit_minute=exit_minute,
                            )

    for decision in (60, 90, 120):
        current = close_at[decision] / day_open - 1.0
        previous = close_at[max(30, decision - 30)]
        recent = close_at[decision] / previous - 1.0
        relative = current.sub(current.median(axis=1), axis=0)
        spy_down = spy_at[decision] <= 0.0
        for exit_minute in (180, 240, 300, 330, 360):
            if exit_minute <= decision:
                continue
            raw = open_at[exit_minute] / open_at[decision + 1] - 1.0
            for count in (3, 5):
                bottom = current.rank(axis=1, ascending=True, method="first") <= count
                for regime_name, regime in (
                    ("all", pd.Series(True, index=dates)),
                    ("spy_down", spy_down),
                ):
                    for bounce in (0.0, 0.0015, 0.003):
                        add_branch(
                            "pullback_recovery",
                            (decision, exit_minute, count, regime_name, bounce),
                            bottom
                            & (current < 0.0)
                            & (recent >= bounce)
                            & (trail3 > -0.15)
                            & regime.to_numpy()[:, None],
                            raw,
                            decision=decision,
                            exit_minute=exit_minute,
                        )
                    for ceiling in (-0.003, -0.005, -0.008):
                        add_branch(
                            "loser_reversal",
                            (decision, exit_minute, count, regime_name, ceiling),
                            bottom
                            & (relative <= ceiling)
                            & (recent < 0.0)
                            & regime.to_numpy()[:, None],
                            raw,
                            decision=decision,
                            exit_minute=exit_minute,
                        )

    def branch_score(branch: Branch) -> tuple[float, float]:
        train_annual = metrics(branch.returns.loc[train_mask])[0]
        validation_annual = metrics(branch.returns.loc[~train_mask])[0]
        return min(train_annual, validation_annual), validation_annual

    def select_frontier(items: list[Branch], *, balanced: int, excess: int) -> list[Branch]:
        balanced_items = sorted(items, key=branch_score, reverse=True)[:balanced]
        excess_items = sorted(
            (
                branch
                for branch in items
                if metrics(branch.returns.loc[train_mask])[0] > 0.0
                and metrics(branch.returns.loc[~train_mask])[0] > 0.0
            ),
            key=lambda branch: information_ratio(
                branch.returns.loc[~train_mask], branch.benchmark.loc[~train_mask]
            ),
            reverse=True,
        )[:excess]
        selected: list[Branch] = []
        seen: set[int] = set()
        for branch in balanced_items + excess_items:
            if id(branch) not in seen:
                selected.append(branch)
                seen.add(id(branch))
        return selected

    strength = select_frontier(
        [branch for branch in branches if branch.family == "volume_strength"],
        balanced=24,
        excess=24,
    )
    recovery = select_frontier(
        [branch for branch in branches if branch.family != "volume_strength"],
        balanced=40,
        excess=40,
    )
    results: list[Result] = []
    passing: list[Result] = []
    for first in strength:
        first_active = first.positions.sum(axis=1) > 0.0
        for second in recovery:
            second_active = second.positions.sum(axis=1) > 0.0
            both = first_active & second_active
            for first_share in (0.25, 0.50, 0.75):
                first_weight = first_active.astype(float)
                second_weight = second_active.astype(float)
                first_weight.loc[both] = first_share
                second_weight.loc[both] = 1.0 - first_share
                returns = first.returns * first_weight + second.returns * second_weight
                benchmark = first.benchmark * first_weight + second.benchmark * second_weight
                components = first.components.mul(first_weight, axis=0) + second.components.mul(
                    second_weight, axis=0
                )
                train_values = metrics(returns.loc[train_mask])
                dev = returns.loc[~train_mask]
                dev_values = metrics(dev)
                boundaries = np.linspace(0, len(dev), 5, dtype=int)
                folds = tuple(
                    metrics(dev.iloc[boundaries[index] : boundaries[index + 1]])[0]
                    for index in range(4)
                )
                positive_pnl = components.loc[~train_mask].sum().clip(lower=0.0)
                concentration = (
                    float(positive_pnl.max() / positive_pnl.sum())
                    if float(positive_pnl.sum()) > 0.0
                    else 1.0
                )
                trades = int(
                    first.positions.loc[~train_mask].gt(0.0).sum().sum()
                    + second.positions.loc[~train_mask].gt(0.0).sum().sum()
                )
                result = Result(
                    families=(first.family, second.family),
                    parameters=(first.parameters, second.parameters, first_share),
                    train_annual=train_values[0],
                    validation_annual=dev_values[0],
                    validation_benchmark_annual=metrics(benchmark.loc[~train_mask])[0],
                    validation_ir=information_ratio(dev, benchmark.loc[~train_mask]),
                    validation_drawdown=dev_values[1],
                    validation_profit_factor=dev_values[2],
                    validation_trades=trades,
                    validation_concentration=concentration,
                    folds=folds,
                )
                results.append(result)
                if (
                    result.train_annual >= 0.08
                    and result.validation_annual >= 0.10
                    and result.validation_ir >= 0.50
                    and result.validation_drawdown >= -0.08
                    and result.validation_profit_factor >= 1.15
                    and result.validation_trades >= 50
                    and result.validation_concentration <= 0.70
                    and sum(value > 0.0 for value in folds) >= 3
                ):
                    passing.append(result)

    print(
        json.dumps(
            {
                "branches": len(branches),
                "strength_frontier": len(strength),
                "recovery_frontier": len(recovery),
                "ensembles": len(results),
                "passing": len(passing),
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
                results,
                key=lambda item: (
                    min(item.train_annual, item.validation_annual),
                    item.validation_ir,
                ),
                reverse=True,
            )[:30],
        ),
        (
            "information_ratio",
            sorted(
                (
                    item
                    for item in results
                    if item.train_annual > 0.0 and item.validation_annual > 0.0
                ),
                key=lambda item: (item.validation_ir, item.validation_annual),
                reverse=True,
            )[:30],
        ),
        (
            "frozen_proposal",
            sorted(
                (
                    item
                    for item in results
                    if item.parameters[0][0] == 45
                    and item.parameters[0][1] in {300, 330, 360}
                    and item.parameters[0][2] == 3
                    and item.parameters[0][3] == 1.5
                    and item.parameters[0][4] == 0.005
                    and item.parameters[0][5] == 0.02
                    and item.parameters[1][0] == 60
                    and item.parameters[1][1] == 360
                    and item.parameters[1][2] in {3, 5}
                    and item.parameters[1][3] == "spy_down"
                    and item.parameters[1][4] == 0.003
                    and item.parameters[2] in {0.25, 0.5}
                ),
                key=lambda item: (
                    item.validation_annual,
                    item.validation_ir,
                ),
                reverse=True,
            ),
        ),
    ):
        for item in items:
            print(json.dumps({"frontier": frontier, **asdict(item)}, sort_keys=True))


if __name__ == "__main__":
    main()
