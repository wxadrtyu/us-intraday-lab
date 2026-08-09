"""Compact, non-authoritative scan of overlap sizing for the asymmetric pair idea."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from us_intraday_lab.long_horizon.hf_snapshot import (
    HfFiveMinuteSnapshotStore,
)
from us_intraday_lab.long_horizon.splits import create_long_horizon_split

ROOT = Path(r"G:\us-intraday-lab")
DATASET_ID = "hf-finnhub-5min-138ddc27bc3de530051d01e30087e449"


def metrics(returns: pd.Series) -> tuple[float, float, float]:
    equity = (1.0 + returns).cumprod()
    years = len(returns) / 252.0
    annual = (float(equity.iloc[-1]) ** (1.0 / years) - 1.0) * 100.0
    drawdown = float((equity / equity.cummax() - 1.0).min()) * 100.0
    positive = float(returns.clip(lower=0.0).sum())
    negative = abs(float(returns.clip(upper=0.0).sum()))
    profit_factor = positive / negative if negative else math.inf
    return annual, drawdown, profit_factor


def main() -> None:
    store = HfFiveMinuteSnapshotStore(root=ROOT, dataset_id=DATASET_ID)
    sessions = store.accepted_sessions
    split = create_long_horizon_split(sessions, split_id="diagnostic")
    bars = store.read_sessions(split.train_sessions + split.validation_sessions)
    bars = bars.sort_values(["symbol", "session_date", "timestamp"], kind="stable")
    grouped = bars.groupby(["symbol", "session_date"], sort=True, observed=True)
    daily = grouped.agg(day_open=("open", "first"), day_close=("close", "last"))
    daily["prior"] = daily.groupby(level="symbol")["day_close"].pct_change().groupby(level="symbol").shift(1)
    daily["trail3"] = daily.groupby(level="symbol")["day_close"].pct_change(3).groupby(level="symbol").shift(1)
    bars["bar_index"] = grouped.cumcount()
    pick = bars.loc[bars["bar_index"].isin([17, 18, 23, 24, 35, 36, 65, 66])]
    closes = pick.pivot_table(index=["symbol", "session_date"], columns="bar_index", values="close")
    next_opens = pick.pivot_table(index=["symbol", "session_date"], columns="bar_index", values="open")
    opens = bars.groupby(["symbol", "session_date"], sort=True, observed=True)["open"].first()

    records: list[dict[str, object]] = []
    for session in split.train_sessions + split.validation_sessions:
        t = ("TQQQ", session)
        s = ("SOXL", session)
        if t not in closes.index or s not in closes.index:
            continue
        # Signal features use the just-closed bar; market fills use the next bar open.
        t_open, s_open = float(opens.loc[t]), float(opens.loc[s])
        records.append(
            {
                "session": session,
                "t_trail3": float(daily.loc[t, "trail3"]),
                "t_entry": float(next_opens.loc[t, 18]),
                "t_exit": float(next_opens.loc[t, 36]),
                "s_rel120": float(closes.loc[s, 23] / s_open - closes.loc[t, 23] / t_open),
                "s_own120": float(closes.loc[s, 23] / s_open - 1.0),
                "s_prior": float(daily.loc[s, "prior"]),
                "t_prior": float(daily.loc[t, "prior"]),
                "s_entry": float(next_opens.loc[s, 24]),
                "s_exit": float(next_opens.loc[s, 66]),
            }
        )
    frame = pd.DataFrame(records).set_index("session")
    train = frame.index.isin(split.train_sessions)
    for max_one in (True, False):
        for lag in (-0.004, -0.005, -0.006):
            for floor in (-0.0175, -0.0200):
                t_signal = frame["t_trail3"] <= -0.10
                s_signal = (
                    (frame["s_rel120"] <= lag)
                    & (frame["s_own120"] >= floor)
                    & (frame["s_prior"] >= -0.03)
                    & (frame["t_prior"] >= -0.03)
                )
                if max_one:
                    s_signal &= ~t_signal
                t_return = frame["t_exit"] / frame["t_entry"] - 1.0
                s_return = frame["s_exit"] / frame["s_entry"] - 1.0
                # Mirrors sequential cash sizing: TQQQ gets 49%; a later SOXL trade
                # gets 49% of remaining cash (about 25%) on overlap days.
                s_weight = np.where(t_signal, 0.49 * (1.0 - 0.49), 0.49)
                combined = t_signal * 0.49 * t_return + s_signal * s_weight * s_return
                tr = metrics(combined.loc[train])
                va = metrics(combined.loc[~train])
                overlap = int((t_signal & s_signal).sum())
                folds = [metrics(part)[0] for part in np.array_split(combined.loc[~train], 4)]
                print(
                    f"one={int(max_one)} lag={lag:.4f} floor={floor:.4f} "
                    f"signals={int(t_signal.sum())}/{int(s_signal.sum())} overlap={overlap} "
                    f"train={tr[0]:.1f}/{tr[1]:.1f}/{tr[2]:.2f} "
                    f"val={va[0]:.1f}/{va[1]:.1f}/{va[2]:.2f} "
                    f"folds={','.join(f'{x:.1f}' for x in folds)}"
                )


if __name__ == "__main__":
    main()
