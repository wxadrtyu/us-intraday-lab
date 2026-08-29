"""Paired-underlying-confirmed exit and re-entry campaign for frozen v1254."""

from __future__ import annotations

from pathlib import Path

import evaluate_full_universe_intraday_v2266_v2365_post_entry_risk as base
import numpy as np

PROPOSAL = Path(__file__).resolve().parents[1] / (
    "research/proposals/full_universe_intraday_v3869_v3968_paired_underlying_risk/proposal.json"
)
PAIR_CONFIRMATION = 0.0
REENTRY_RECOVERY = 0.0025
PROFIT_ACTIVATION = 0.015
SAME_SYMBOL_CAP = 0.775
ORIGINAL_BUILD_STREAMS = base.build_streams


def pair_confirmation(mode: str) -> float:
    prefix = "anchor_only_pair_"
    if not mode.startswith(prefix):
        raise ValueError("UNKNOWN_PAIR_CONFIRMATION_MODE")
    threshold = float(mode.removeprefix(prefix))
    if not -0.02 <= threshold <= 0.02:
        raise ValueError("PAIR_CONFIRMATION_OUT_OF_RANGE")
    return threshold


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
    safe_asset, rows = np.maximum(selected, 0), cube.rows
    paired = np.where(selected == 3, 1, np.where(selected == 4, 10, 0))
    entry_price = cube.opens[rows, entry, safe_asset]
    paired_entry = cube.opens[rows, entry, paired]
    market_entry = cube.opens[rows, entry, 0]
    exit_bar = np.full(len(cube.sessions), fixed_exit, dtype=int)
    peak, unresolved = entry_price.copy(), active.copy()
    invalid = np.zeros(len(cube.sessions), dtype=bool)
    first_monitor = entry + minimum_holding_bars - 1
    for bar in range(int(first_monitor.min()), fixed_exit):
        eligible = unresolved & (bar >= first_monitor)
        complete = (
            (cube.last[rows, bar, safe_asset] >= bar * 5 + 4 - cube.boundary_tolerance)
            & (cube.last[rows, bar, paired] >= bar * 5 + 4 - cube.boundary_tolerance)
        )
        close = cube.closes[rows, bar, safe_asset]
        paired_close = cube.closes[rows, bar, paired]
        observed = (
            eligible
            & complete
            & np.isfinite(close)
            & np.isfinite(paired_close)
            & (close > 0)
            & (paired_close > 0)
        )
        peak[observed] = np.maximum(peak[observed], close[observed])
        hard = (close / entry_price - 1.0 <= -hard_stop) & (
            paired_close / paired_entry - 1.0 <= PAIR_CONFIRMATION
        )
        trailing = (peak / entry_price - 1.0 >= PROFIT_ACTIVATION) & (
            close / peak - 1.0 <= -trailing_drawdown
        )
        breach = observed & (hard | trailing)
        if not breach.any():
            continue
        next_bar = bar + 1
        executable = breach & (
            (cube.first[rows, next_bar, safe_asset] <= next_bar * 5 + cube.boundary_tolerance)
            & np.isfinite(cube.opens[rows, next_bar, safe_asset])
            & np.isfinite(cube.opens[rows, next_bar, paired])
            & (cube.opens[rows, next_bar, safe_asset] > 0)
            & (cube.opens[rows, next_bar, paired] > 0)
        )
        exit_bar[executable] = next_bar
        invalid |= breach & ~executable
        unresolved &= ~breach

    stopped = active & ~invalid & (exit_bar < fixed_exit)
    reentry_bar = np.full(len(cube.sessions), -1, dtype=int)
    waiting = stopped.copy()
    exit_price = cube.opens[rows, exit_bar, safe_asset]
    paired_exit = cube.opens[rows, exit_bar, paired]
    for bar in range(int(np.min(exit_bar[stopped], initial=fixed_exit)), fixed_exit):
        eligible = waiting & (bar >= exit_bar)
        complete = (
            (cube.last[rows, bar, safe_asset] >= bar * 5 + 4 - cube.boundary_tolerance)
            & (cube.last[rows, bar, paired] >= bar * 5 + 4 - cube.boundary_tolerance)
        )
        close = cube.closes[rows, bar, safe_asset]
        paired_close = cube.closes[rows, bar, paired]
        recovery = (
            eligible
            & complete
            & np.isfinite(close)
            & np.isfinite(paired_close)
            & (close / exit_price - 1.0 >= REENTRY_RECOVERY)
            & (paired_close / paired_exit - 1.0 >= 0.0)
        )
        if not recovery.any():
            continue
        next_bar = bar + 1
        executable = recovery & (
            (cube.first[rows, next_bar, safe_asset] <= next_bar * 5 + cube.boundary_tolerance)
            & np.isfinite(cube.opens[rows, next_bar, safe_asset])
            & np.isfinite(cube.opens[rows, next_bar, paired])
            & (cube.opens[rows, next_bar, safe_asset] > 0)
            & (cube.opens[rows, next_bar, paired] > 0)
        )
        reentry_bar[executable] = next_bar
        waiting &= ~recovery

    valid, final_active = ~invalid, active & ~invalid
    values, benchmark = np.zeros(len(cube.sessions)), np.zeros(len(cube.sessions))
    one_leg = final_active & (reentry_bar < 0)
    values[one_leg] = (
        cube.opens[rows[one_leg], exit_bar[one_leg], safe_asset[one_leg]] / entry_price[one_leg]
        - 1.0
        - cost
    )
    benchmark[one_leg] = (
        cube.opens[rows[one_leg], exit_bar[one_leg], 0] / market_entry[one_leg] - 1.0
    )
    reentered = final_active & (reentry_bar >= 0)
    first_leg = cube.opens[rows[reentered], exit_bar[reentered], safe_asset[reentered]] / entry_price[reentered]
    second_leg = (
        cube.opens[rows[reentered], fixed_exit, safe_asset[reentered]]
        / cube.opens[rows[reentered], reentry_bar[reentered], safe_asset[reentered]]
    )
    values[reentered] = first_leg * second_leg - 1.0 - 2.0 * cost
    first_benchmark = cube.opens[rows[reentered], exit_bar[reentered], 0] / market_entry[reentered]
    second_benchmark = (
        cube.opens[rows[reentered], fixed_exit, 0]
        / cube.opens[rows[reentered], reentry_bar[reentered], 0]
    )
    benchmark[reentered] = first_benchmark * second_benchmark - 1.0
    return (
        base.prior.v12.ReturnStream(
            values,
            benchmark,
            final_active,
            final_active.astype(int) + reentered.astype(int),
        ),
        valid,
        exit_bar,
    )


def build_streams(cube, development, record, models, definition):
    global PAIR_CONFIRMATION
    PAIR_CONFIRMATION = pair_confirmation(definition["application_mode"])
    stop_definition = {**definition, "application_mode": "anchor_only"}
    streams, valids, exits = ORIGINAL_BUILD_STREAMS(
        cube, development, record, models, stop_definition
    )
    output = []
    for index, delay in enumerate((0, 0, 1)):
        anchor_selected, _, anchor_active = base.anchor_route(cube, models, delay)
        component_selected, _, component_active = base.component_route(cube, record, delay)
        same = (anchor_selected == component_selected) & anchor_active & component_active
        output.append(base.risk.scaled(streams[index], np.where(same, SAME_SYMBOL_CAP, 1.0)))
    return tuple(output), valids, exits


if __name__ == "__main__":
    base.PROPOSAL = PROPOSAL
    base.CODE_PATH = Path(__file__)
    base.CODE_DEPENDENCIES = (Path(base.__file__),)
    base.stopped_raw = stopped_raw
    base.build_streams = build_streams
    base.main()
