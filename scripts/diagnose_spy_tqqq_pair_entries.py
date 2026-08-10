"""Development-only scan of simultaneous SPY/TQQQ causal pair entries."""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd

from us_intraday_lab.long_horizon.hf_snapshot import HfFiveMinuteSnapshotStore
from us_intraday_lab.long_horizon.splits import create_long_horizon_split

ROOT = Path(r"G:\us-intraday-lab")
DATASET_ID = "hf-finnhub-5min-b78802459222d4baef0985e726232461"
PAIR_COST_1_5X = 0.00025


def metrics(returns: pd.Series) -> tuple[float, float, float]:
    equity = (1.0 + returns).cumprod()
    annual = (float(equity.iloc[-1]) ** (252.0 / len(returns)) - 1.0) * 100.0
    drawdown = float((equity / equity.cummax() - 1.0).min()) * 100.0
    gains = float(returns.clip(lower=0.0).sum())
    losses = abs(float(returns.clip(upper=0.0).sum()))
    return annual, drawdown, gains / losses if losses else math.inf


def ir(returns: pd.Series, benchmark: pd.Series) -> float:
    active = returns - benchmark
    return float(active.mean() / active.std(ddof=1) * math.sqrt(252.0))


def main() -> None:
    store = HfFiveMinuteSnapshotStore(root=ROOT, dataset_id=DATASET_ID)
    split = create_long_horizon_split(store.accepted_sessions, split_id="diagnostic")
    sessions = split.train_sessions + split.validation_sessions
    index = pd.Index(sessions)
    train_mask = index.isin(split.train_sessions)
    bars = store.read_sessions(sessions).sort_values(
        ["symbol", "session_date", "timestamp"], kind="stable"
    )
    groups = bars.groupby(["symbol", "session_date"], sort=True, observed=True)
    bars["bar_index"] = groups.cumcount()
    day_open = groups["open"].first()
    day_close = groups["close"].last()
    prior = day_close.groupby(level="symbol").pct_change().groupby(level="symbol").shift(1)
    trail3 = day_close.groupby(level="symbol").pct_change(3).groupby(level="symbol").shift(1)
    decisions = (30, 60, 90, 120, 150, 180)
    exits = (120, 180, 240, 330)
    wanted_indexes = sorted(
        {minute // 5 - 1 for minute in decisions} | {minute // 5 for minute in (*decisions, *exits)}
    )
    wanted = bars.loc[bars["bar_index"].isin(wanted_indexes)]
    closes = wanted.pivot_table(
        index=["symbol", "session_date"], columns="bar_index", values="close"
    )
    opens = wanted.pivot_table(index=["symbol", "session_date"], columns="bar_index", values="open")

    def series(values: pd.Series, symbol: str) -> pd.Series:
        rows = pd.MultiIndex.from_product([[symbol], sessions])
        return pd.Series(values.reindex(rows).to_numpy(), index=index)

    spy_day_open = series(day_open, "SPY")
    tqqq_day_open = series(day_open, "TQQQ")
    spy_prior = series(prior, "SPY")
    tqqq_prior = series(prior, "TQQQ")
    spy_trail3 = series(trail3, "SPY")
    tqqq_trail3 = series(trail3, "TQQQ")
    benchmark_close = series(day_close, "SPY")
    benchmark = benchmark_close.pct_change(fill_method=None).fillna(0.0)
    retained: list[tuple[float, str]] = []

    def evaluate(
        family: str,
        parameters: tuple[object, ...],
        signal: pd.Series,
        spy_raw: pd.Series,
        tqqq_raw: pd.Series,
    ) -> None:
        spy_component = signal.astype(float) * (0.49 * spy_raw - 0.00015)
        tqqq_component = signal.astype(float) * (0.25 * tqqq_raw - 0.00010)
        returns = spy_component + tqqq_component
        train = metrics(returns.loc[train_mask])
        validation_returns = returns.loc[~train_mask]
        validation = metrics(validation_returns)
        boundaries = (
            (0, len(validation_returns) // 4),
            (len(validation_returns) // 4, len(validation_returns) // 2),
            (len(validation_returns) // 2, 3 * len(validation_returns) // 4),
            (3 * len(validation_returns) // 4, len(validation_returns)),
        )
        folds = tuple(metrics(validation_returns.iloc[start:stop])[0] for start, stop in boundaries)
        validation_ir = ir(validation_returns, benchmark.loc[~train_mask])
        spy_profit = float(spy_component.sum())
        tqqq_profit = float(tqqq_component.sum())
        concentration = (
            max(spy_profit, tqqq_profit) / (spy_profit + tqqq_profit)
            if spy_profit > 0.0 and tqqq_profit > 0.0
            else 1.0
        )
        if (
            train[0] >= 8.0
            and validation[0] >= 10.0
            and validation_ir >= 0.50
            and validation[1] >= -8.0
            and validation[2] >= 1.15
            and min(folds) > 0.0
            and concentration <= 0.70
        ):
            line = (
                f"{family} p={parameters} n={int(signal.sum())} "
                f"train={train[0]:.1f}/{train[1]:.1f}/{train[2]:.2f} "
                f"val={validation[0]:.1f}/{validation[1]:.1f}/{validation[2]:.2f} "
                f"ir={validation_ir:.2f} conc={concentration:.2f} "
                f"folds={','.join(f'{value:.1f}' for value in folds)}"
            )
            retained.append((min(train[0], validation[0]), line))

    for decision in decisions:
        decision_index = decision // 5 - 1
        entry_index = decision // 5
        spy_decision = series(closes[decision_index], "SPY")
        tqqq_decision = series(closes[decision_index], "TQQQ")
        spy_current = spy_decision / spy_day_open - 1.0
        tqqq_current = tqqq_decision / tqqq_day_open - 1.0
        residual = tqqq_current - 3.0 * spy_current
        for exit_minute in exits:
            if exit_minute <= decision:
                continue
            spy_entry = series(opens[entry_index], "SPY")
            tqqq_entry = series(opens[entry_index], "TQQQ")
            spy_exit = series(opens[exit_minute // 5], "SPY")
            tqqq_exit = series(opens[exit_minute // 5], "TQQQ")
            spy_raw = spy_exit / spy_entry - 1.0
            tqqq_raw = tqqq_exit / tqqq_entry - 1.0
            for spy_min in (0.0015, 0.0025, 0.004, 0.006, 0.008, 0.01):
                for tqqq_min in (0.004, 0.006, 0.01, 0.015, 0.02, 0.03):
                    signal = (
                        (spy_current >= spy_min)
                        & (tqqq_current >= tqqq_min)
                        & (spy_prior >= -0.03)
                        & (tqqq_prior >= -0.06)
                    )
                    evaluate(
                        "pair_momentum",
                        (decision, exit_minute, spy_min, tqqq_min),
                        signal,
                        spy_raw,
                        tqqq_raw,
                    )
            for spy_max in (-0.0025, -0.004, -0.006, -0.008, -0.012, -0.016):
                for tqqq_max in (-0.0075, -0.012, -0.018, -0.025, -0.035, -0.05):
                    signal = (
                        (spy_current <= spy_max)
                        & (tqqq_current <= tqqq_max)
                        & (spy_current >= -0.025)
                        & (tqqq_current >= -0.075)
                    )
                    evaluate(
                        "pair_reversal",
                        (decision, exit_minute, spy_max, tqqq_max),
                        signal,
                        spy_raw,
                        tqqq_raw,
                    )
            for residual_max in (-0.003, -0.005, -0.008, -0.012, -0.018, -0.025):
                for spy_floor in (-0.01, -0.005, 0.0, 0.0025):
                    signal = (
                        (residual <= residual_max)
                        & (spy_current >= spy_floor)
                        & (tqqq_current >= -0.06)
                        & (spy_prior >= -0.03)
                        & (tqqq_prior >= -0.06)
                    )
                    evaluate(
                        "tqqq_residual_laggard",
                        (decision, exit_minute, residual_max, spy_floor),
                        signal,
                        spy_raw,
                        tqqq_raw,
                    )
            for spy_crash in (-0.02, -0.03, -0.04, -0.05):
                for tqqq_crash in (-0.06, -0.08, -0.10, -0.12, -0.15):
                    signal = (spy_trail3 <= spy_crash) & (tqqq_trail3 <= tqqq_crash)
                    evaluate(
                        "pair_trail3_crash",
                        (decision, exit_minute, spy_crash, tqqq_crash),
                        signal,
                        spy_raw,
                        tqqq_raw,
                    )

    for _score, line in sorted(retained, reverse=True)[:50]:
        print(line)
    print(f"passing_cells={len(retained)}")


if __name__ == "__main__":
    main()
