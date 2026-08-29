"""Same-symbol deleveraging with a conservatively costed SPY replacement sleeve."""

from __future__ import annotations

from pathlib import Path

import evaluate_full_universe_intraday_v2266_v2365_post_entry_risk as base
import evaluate_full_universe_intraday_v2366_v2465_conditional_exit as conditional
import numpy as np

PROPOSAL = Path(__file__).resolve().parents[1] / (
    "research/proposals/full_universe_intraday_v2766_v2865_spy_deleveraging/proposal.json"
)
ORIGINAL_BUILD_STREAMS = base.build_streams


def mode_parameters(mode: str) -> tuple[float, float]:
    prefix = "same_cap_"
    separator = "_spy_replace_"
    if not mode.startswith(prefix) or separator not in mode:
        raise ValueError("UNKNOWN_SPY_DELEVERAGING_MODE")
    cap_text, replacement_text = mode.removeprefix(prefix).split(separator, maxsplit=1)
    cap, replacement = float(cap_text), float(replacement_text)
    if not 0 < cap <= 1 or not 0 <= replacement <= 1:
        raise ValueError("SPY_DELEVERAGING_PARAMETER_OUT_OF_RANGE")
    return cap, replacement


def add_spy_replacement(stream, same: np.ndarray, cap: float, replacement: float, cost: float):
    leveraged_multiplier = np.where(same, cap, 1.0)
    replacement_weight = np.where(same, (1.0 - cap) * replacement, 0.0)
    replacement_return = stream.benchmark - np.where(stream.active, cost, 0.0)
    active_replacement = stream.active & (replacement_weight > 0)
    return base.prior.v12.ReturnStream(
        stream.values * leveraged_multiplier + replacement_return * replacement_weight,
        stream.benchmark * (leveraged_multiplier + replacement_weight),
        stream.active | active_replacement,
        stream.component_trades + active_replacement.astype(int),
    )


def build_streams(cube, development, record, models, definition):
    cap, replacement = mode_parameters(definition["application_mode"])
    stop_definition = {**definition, "application_mode": "both_sleeves"}
    streams, valids, exits = ORIGINAL_BUILD_STREAMS(
        cube, development, record, models, stop_definition
    )
    output = []
    scenarios = (
        (base.prior.v34.STANDARD_COST, 0),
        (base.prior.v34.STRESS_COST, 0),
        (base.prior.v34.STANDARD_COST, 1),
    )
    for index, (cost, delay) in enumerate(scenarios):
        anchor_selected, _, anchor_active = base.anchor_route(cube, models, delay)
        component_selected, _, component_active = base.component_route(cube, record, delay)
        same = (anchor_selected == component_selected) & anchor_active & component_active
        output.append(add_spy_replacement(streams[index], same, cap, replacement, cost))
    return tuple(output), valids, exits


if __name__ == "__main__":
    base.PROPOSAL = PROPOSAL
    base.CODE_PATH = Path(__file__)
    base.CODE_DEPENDENCIES = (Path(base.__file__), Path(conditional.__file__))
    base.stopped_raw = conditional.stopped_raw
    base.build_streams = build_streams
    base.main()
