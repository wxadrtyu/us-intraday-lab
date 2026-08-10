"""Development-only causal scan of SPY/IWM intraday branch families."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from us_intraday_lab.long_horizon.hf_snapshot import HfFiveMinuteSnapshotStore
from us_intraday_lab.long_horizon.splits import create_long_horizon_split

ROOT = Path(r"G:\us-intraday-lab")
DATASET_ID = "hf-finnhub-5min-d1b237e2ff9714163492f900cb32853e"
COST_1_5X_PER_TRADE = 0.00015


@dataclass(frozen=True)
class Result:
    family: str
    symbol: str
    parameters: tuple[object, ...]
    signal: pd.Series
    returns: pd.Series
    train_annual: float
    validation_annual: float
    validation_ir: float
    validation_drawdown: float
    validation_profit_factor: float
    folds: tuple[float, ...]


def metrics(returns: pd.Series) -> tuple[float, float, float]:
    equity = (1.0 + returns).cumprod()
    annual = (float(equity.iloc[-1]) ** (252.0 / len(returns)) - 1.0) * 100.0
    drawdown = float((equity / equity.cummax() - 1.0).min()) * 100.0
    gains = float(returns.clip(lower=0.0).sum())
    losses = abs(float(returns.clip(upper=0.0).sum()))
    return annual, drawdown, gains / losses if losses else math.inf


def information_ratio(returns: pd.Series, benchmark: pd.Series) -> float:
    active = returns - benchmark
    standard_deviation = float(active.std(ddof=1))
    return float(active.mean() * 252.0 / (standard_deviation * math.sqrt(252.0)))


def main() -> None:
    store = HfFiveMinuteSnapshotStore(root=ROOT, dataset_id=DATASET_ID)
    split = create_long_horizon_split(store.accepted_sessions, split_id="diagnostic")
    sessions = split.train_sessions + split.validation_sessions
    bars = store.read_sessions(sessions).sort_values(
        ["symbol", "session_date", "timestamp"], kind="stable"
    )
    groups = bars.groupby(["symbol", "session_date"], sort=True, observed=True)
    bars["bar_index"] = groups.cumcount()
    daily_open = groups["open"].first()
    daily_close = groups["close"].last()
    prior = daily_close.groupby(level="symbol").pct_change().groupby(level="symbol").shift(1)
    trail3 = daily_close.groupby(level="symbol").pct_change(3).groupby(level="symbol").shift(1)
    indexes = sorted(
        {minute // 5 - 1 for minute in (60, 90, 120, 150)}
        | {minute // 5 for minute in (60, 90, 120, 150, 180, 240, 330)}
    )
    wanted = bars.loc[bars["bar_index"].isin(indexes)]
    closes = wanted.pivot_table(
        index=["symbol", "session_date"], columns="bar_index", values="close"
    )
    opens = wanted.pivot_table(index=["symbol", "session_date"], columns="bar_index", values="open")
    session_index = pd.Index(sessions)
    train_mask = session_index.isin(split.train_sessions)
    spy_close = daily_close.loc["SPY"].reindex(session_index)
    benchmark = spy_close.pct_change(fill_method=None).fillna(0.0)
    results: list[Result] = []

    def evaluate(
        family: str,
        symbol: str,
        parameters: tuple[object, ...],
        signal: pd.Series,
        raw_trade_return: pd.Series,
    ) -> None:
        portfolio_return = signal.astype(float) * (0.49 * raw_trade_return - COST_1_5X_PER_TRADE)
        train = metrics(portfolio_return.loc[train_mask])
        validation_returns = portfolio_return.loc[~train_mask]
        validation = metrics(validation_returns)
        folds = tuple(
            metrics(validation_returns.iloc[start:stop])[0]
            for start, stop in (
                (0, len(validation_returns) // 4),
                (len(validation_returns) // 4, len(validation_returns) // 2),
                (len(validation_returns) // 2, 3 * len(validation_returns) // 4),
                (3 * len(validation_returns) // 4, len(validation_returns)),
            )
        )
        ir = information_ratio(validation_returns, benchmark.loc[~train_mask])
        if train[0] > 0.0 and validation[0] > 0.0 and min(folds) > -3.0:
            results.append(
                Result(
                    family,
                    symbol,
                    parameters,
                    signal,
                    portfolio_return,
                    train[0],
                    validation[0],
                    ir,
                    validation[1],
                    validation[2],
                    folds,
                )
            )

    for symbol, peer in (("SPY", "IWM"), ("IWM", "SPY")):
        symbol_rows = pd.MultiIndex.from_product([[symbol], sessions])
        peer_rows = pd.MultiIndex.from_product([[peer], sessions])
        symbol_prior = pd.Series(prior.reindex(symbol_rows).to_numpy(), index=session_index)
        peer_prior = pd.Series(prior.reindex(peer_rows).to_numpy(), index=session_index)
        symbol_trail3 = pd.Series(trail3.reindex(symbol_rows).to_numpy(), index=session_index)
        for decision in (60, 90, 120, 150):
            decision_index = decision // 5 - 1
            entry_index = decision // 5
            symbol_open = pd.Series(daily_open.reindex(symbol_rows).to_numpy(), index=session_index)
            peer_open = pd.Series(daily_open.reindex(peer_rows).to_numpy(), index=session_index)
            symbol_decision = pd.Series(
                closes.reindex(symbol_rows)[decision_index].to_numpy(), index=session_index
            )
            peer_decision = pd.Series(
                closes.reindex(peer_rows)[decision_index].to_numpy(), index=session_index
            )
            own_return = symbol_decision / symbol_open - 1.0
            relative_return = own_return - (peer_decision / peer_open - 1.0)
            for exit_minute in (180, 240, 330):
                if exit_minute <= decision:
                    continue
                entry = pd.Series(
                    opens.reindex(symbol_rows)[entry_index].to_numpy(), index=session_index
                )
                exit_price = pd.Series(
                    opens.reindex(symbol_rows)[exit_minute // 5].to_numpy(), index=session_index
                )
                raw_return = exit_price / entry - 1.0
                for relative_max in (-0.0015, -0.0025, -0.0035, -0.005, -0.0075, -0.01):
                    for own_floor in (-0.005, -0.01, -0.015, -0.02, -0.03):
                        signal = (
                            (relative_return <= relative_max)
                            & (own_return >= own_floor)
                            & (symbol_prior >= -0.03)
                            & (peer_prior >= -0.03)
                        )
                        evaluate(
                            "relative_laggard",
                            symbol,
                            (decision, exit_minute, relative_max, own_floor),
                            signal,
                            raw_return,
                        )
                crash_thresholds = (
                    (-0.02, -0.03, -0.04, -0.05)
                    if symbol == "SPY"
                    else (-0.03, -0.04, -0.05, -0.06, -0.08)
                )
                for threshold in crash_thresholds:
                    evaluate(
                        "trail3_crash",
                        symbol,
                        (decision, exit_minute, threshold),
                        symbol_trail3 <= threshold,
                        raw_return,
                    )
                for current_max in (-0.003, -0.005, -0.0075, -0.01, -0.015, -0.02):
                    for own_floor in (-0.01, -0.015, -0.02, -0.03, -0.04):
                        if own_floor >= current_max:
                            continue
                        signal = (
                            (own_return <= current_max)
                            & (own_return >= own_floor)
                            & (symbol_prior >= -0.03)
                        )
                        evaluate(
                            "open_reversal",
                            symbol,
                            (decision, exit_minute, current_max, own_floor),
                            signal,
                            raw_return,
                        )
                for current_min in (0.0025, 0.004, 0.006, 0.008, 0.012, 0.016):
                    signal = (
                        (own_return >= current_min)
                        & (symbol_prior >= -0.03)
                        & (peer_prior >= -0.03)
                    )
                    evaluate(
                        "open_momentum",
                        symbol,
                        (decision, exit_minute, current_min),
                        signal,
                        raw_return,
                    )

    ranked = sorted(
        results,
        key=lambda item: (
            min(item.train_annual, item.validation_annual),
            item.validation_ir,
        ),
        reverse=True,
    )
    for item in ranked[:50]:
        print(
            f"{item.family:17s} {item.symbol} p={item.parameters} "
            f"n={int(item.signal.sum())} train={item.train_annual:.1f} "
            f"val={item.validation_annual:.1f} ir={item.validation_ir:.2f} "
            f"mdd={item.validation_drawdown:.1f} pf={item.validation_profit_factor:.2f} "
            f"folds={','.join(f'{value:.1f}' for value in item.folds)}"
        )
    print(f"retained_cells={len(results)}")


if __name__ == "__main__":
    main()
