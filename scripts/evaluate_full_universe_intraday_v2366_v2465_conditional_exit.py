"""Joint ETF/market loss exit plus activated profit-giveback protection."""

from __future__ import annotations

from pathlib import Path

import evaluate_full_universe_intraday_v2266_v2365_post_entry_risk as base
import numpy as np

PROPOSAL = Path(__file__).resolve().parents[1] / (
    "research/proposals/full_universe_intraday_v2366_v2465_conditional_exit/proposal.json"
)
MARKET_CONFIRMATION = -0.0025
PROFIT_ACTIVATION = 0.015


def stopped_raw(
    cube,
    selected: np.ndarray,
    entry: np.ndarray,
    active: np.ndarray,
    fixed_exit: int,
    cost: float,
    hard_stop: float,
    trailing_drawdown: float,
    minimum_holding_bars: int,
) -> tuple[object, np.ndarray, np.ndarray]:
    safe_asset = np.maximum(selected, 0)
    rows = cube.rows
    entry_price = cube.opens[rows, entry, safe_asset]
    market_entry = cube.opens[rows, entry, 0]
    exit_bar = np.full(len(cube.sessions), fixed_exit, dtype=int)
    peak = entry_price.copy()
    unresolved = active.copy()
    invalid = np.zeros(len(cube.sessions), dtype=bool)
    first_monitor = entry + minimum_holding_bars - 1
    for bar in range(int(first_monitor.min()), fixed_exit):
        eligible = unresolved & (bar >= first_monitor)
        asset_complete = cube.last[rows, bar, safe_asset] >= (
            bar * 5 + 4 - cube.boundary_tolerance
        )
        market_complete = cube.last[:, bar, 0] >= bar * 5 + 4 - cube.boundary_tolerance
        close = cube.closes[rows, bar, safe_asset]
        market_close = cube.closes[:, bar, 0]
        observed = (
            eligible
            & asset_complete
            & market_complete
            & np.isfinite(close)
            & np.isfinite(market_close)
            & (close > 0)
            & (market_close > 0)
        )
        peak[observed] = np.maximum(peak[observed], close[observed])
        asset_loss = close / entry_price - 1.0
        market_loss = market_close / market_entry - 1.0
        hard_breach = (asset_loss <= -hard_stop) & (market_loss <= MARKET_CONFIRMATION)
        profit_active = peak / entry_price - 1.0 >= PROFIT_ACTIVATION
        profit_breach = profit_active & ((close / peak - 1.0) <= -trailing_drawdown)
        breach = observed & (hard_breach | profit_breach)
        if not breach.any():
            continue
        next_bar = bar + 1
        next_open_ok = (
            (cube.first[rows, next_bar, safe_asset] <= next_bar * 5 + cube.boundary_tolerance)
            & np.isfinite(cube.opens[rows, next_bar, safe_asset])
            & np.isfinite(cube.opens[:, next_bar, 0])
            & (cube.opens[rows, next_bar, safe_asset] > 0)
            & (cube.opens[:, next_bar, 0] > 0)
        )
        executable = breach & next_open_ok
        exit_bar[executable] = next_bar
        invalid |= breach & ~next_open_ok
        unresolved &= ~breach
    valid = ~invalid
    final_active = active & valid
    values, benchmark = np.zeros(len(cube.sessions)), np.zeros(len(cube.sessions))
    values[final_active] = (
        cube.opens[rows[final_active], exit_bar[final_active], safe_asset[final_active]]
        / entry_price[final_active]
        - 1.0
        - cost
    )
    benchmark[final_active] = (
        cube.opens[rows[final_active], exit_bar[final_active], 0]
        / market_entry[final_active]
        - 1.0
    )
    stream = base.prior.v12.ReturnStream(
        values, benchmark, final_active, final_active.astype(int)
    )
    return stream, valid, exit_bar


if __name__ == "__main__":
    base.PROPOSAL = PROPOSAL
    base.CODE_PATH = Path(__file__)
    base.stopped_raw = stopped_raw
    base.main()
