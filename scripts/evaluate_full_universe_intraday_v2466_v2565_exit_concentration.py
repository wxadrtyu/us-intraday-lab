"""Conditional exits combined with a same-symbol gross concentration cap."""

from __future__ import annotations

from pathlib import Path

import evaluate_full_universe_intraday_v2266_v2365_post_entry_risk as base
import evaluate_full_universe_intraday_v2366_v2465_conditional_exit as conditional
import numpy as np

PROPOSAL = Path(__file__).resolve().parents[1] / (
    "research/proposals/full_universe_intraday_v2466_v2565_exit_concentration/proposal.json"
)
ORIGINAL_BUILD_STREAMS = base.build_streams


def concentration_cap(mode: str) -> float:
    prefix = "both_sleeves_cap_"
    if not mode.startswith(prefix):
        raise ValueError("UNKNOWN_CONCENTRATION_MODE")
    cap = float(mode.removeprefix(prefix))
    if not 0 < cap <= 1:
        raise ValueError("CONCENTRATION_CAP_OUT_OF_RANGE")
    return cap


def build_streams(cube, development, record, models, definition):
    cap = concentration_cap(definition["application_mode"])
    stop_definition = {**definition, "application_mode": "both_sleeves"}
    streams, valids, exits = ORIGINAL_BUILD_STREAMS(
        cube, development, record, models, stop_definition
    )
    output = []
    for index, delay in enumerate((0, 0, 1)):
        anchor_selected, _, anchor_active = base.anchor_route(cube, models, delay)
        component_selected, _, component_active = base.component_route(cube, record, delay)
        same = (anchor_selected == component_selected) & anchor_active & component_active
        multiplier = np.where(same, cap, 1.0)
        output.append(base.risk.scaled(streams[index], multiplier))
    return tuple(output), valids, exits


if __name__ == "__main__":
    base.PROPOSAL = PROPOSAL
    base.CODE_PATH = Path(__file__)
    base.CODE_DEPENDENCIES = (Path(base.__file__), Path(conditional.__file__))
    base.stopped_raw = conditional.stopped_raw
    base.build_streams = build_streams
    base.main()
