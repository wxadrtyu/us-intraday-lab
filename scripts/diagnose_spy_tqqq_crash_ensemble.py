"""Development-only scan for a two-symbol crash-rebound ensemble."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from us_intraday_lab.long_horizon.hf_snapshot import HfFiveMinuteSnapshotStore
from us_intraday_lab.long_horizon.splits import create_long_horizon_split

ROOT = Path(r"G:\us-intraday-lab")
DATASET_ID = "hf-finnhub-5min-b78802459222d4baef0985e726232461"


def metrics(returns: pd.Series) -> tuple[float, float, float]:
    equity = (1.0 + returns).cumprod()
    annual = (float(equity.iloc[-1]) ** (252.0 / len(returns)) - 1.0) * 100.0
    drawdown = float((equity / equity.cummax() - 1.0).min()) * 100.0
    gains = float(returns.clip(lower=0.0).sum())
    losses = abs(float(returns.clip(upper=0.0).sum()))
    return annual, drawdown, gains / losses if losses else math.inf


def main() -> None:
    store = HfFiveMinuteSnapshotStore(root=ROOT, dataset_id=DATASET_ID)
    split = create_long_horizon_split(store.accepted_sessions, split_id="diagnostic")
    sessions = split.train_sessions + split.validation_sessions
    bars = store.read_sessions(sessions).sort_values(
        ["symbol", "session_date", "timestamp"], kind="stable"
    )
    groups = bars.groupby(["symbol", "session_date"], sort=True, observed=True)
    bars["bar_index"] = groups.cumcount()
    daily_close = groups["close"].last()
    trail3 = daily_close.groupby(level="symbol").pct_change(3).groupby(level="symbol").shift(1)
    wanted = bars.loc[bars["bar_index"].isin([18, 24, 36, 48, 66])]
    opens = wanted.pivot_table(
        index=["symbol", "session_date"], columns="bar_index", values="open"
    )
    train_mask = pd.Index(sessions).isin(split.train_sessions)
    found: list[tuple[float, str]] = []
    for spy_threshold in (-0.02, -0.025, -0.03, -0.035, -0.04, -0.05):
        for tqqq_threshold in (-0.08, -0.09, -0.10, -0.11, -0.12):
            for t_exit in (36, 48, 66):
                for s_exit in (48, 66):
                    daily_returns: list[float] = []
                    spy_pnl = 0.0
                    tqqq_pnl = 0.0
                    counts = [0, 0]
                    for session in sessions:
                        t = ("TQQQ", session)
                        s = ("SPY", session)
                        value = 0.0
                        if float(trail3.loc[t]) <= tqqq_threshold:
                            value = 0.49 * (float(opens.loc[t, t_exit]) / float(opens.loc[t, 18]) - 1.0) - 0.00015
                            tqqq_pnl += value
                            counts[1] += 1
                        elif float(trail3.loc[s]) <= spy_threshold:
                            value = 0.49 * (float(opens.loc[s, s_exit]) / float(opens.loc[s, 24]) - 1.0) - 0.00015
                            spy_pnl += value
                            counts[0] += 1
                        daily_returns.append(value)
                    returns = pd.Series(daily_returns, index=sessions)
                    train = metrics(returns.loc[train_mask])
                    validation = metrics(returns.loc[~train_mask])
                    folds = [metrics(part)[0] for part in np.array_split(returns.loc[~train_mask], 4)]
                    concentration = max(spy_pnl, tqqq_pnl) / (spy_pnl + tqqq_pnl) if spy_pnl > 0 and tqqq_pnl > 0 else 1.0
                    if (
                        train[0] >= 8.0
                        and validation[0] >= 10.0
                        and min(folds) > 0.0
                        and concentration <= 0.70
                    ):
                        line = (
                            f"spy={spy_threshold:.3f} tq={tqqq_threshold:.2f} exits={t_exit}/{s_exit} "
                            f"n={counts[0]}/{counts[1]} train={train[0]:.1f}/{train[1]:.1f}/{train[2]:.2f} "
                            f"val={validation[0]:.1f}/{validation[1]:.1f}/{validation[2]:.2f} "
                            f"conc={concentration:.2f} folds={','.join(f'{x:.1f}' for x in folds)}"
                        )
                        found.append((validation[0], line))
    for _score, line in sorted(found, reverse=True)[:30]:
        print(line)
    print(f"passing_cells={len(found)}")


if __name__ == "__main__":
    main()
