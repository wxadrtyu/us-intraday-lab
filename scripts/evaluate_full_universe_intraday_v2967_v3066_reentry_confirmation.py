"""One-reentry campaign varying the causal recovery confirmation threshold."""

from __future__ import annotations

from pathlib import Path

import evaluate_full_universe_intraday_v2266_v2365_post_entry_risk as base
import evaluate_full_universe_intraday_v2866_v2965_one_reentry as reentry
import numpy as np

PROPOSAL = Path(__file__).resolve().parents[1] / (
    "research/proposals/full_universe_intraday_v2967_v3066_reentry_confirmation/proposal.json"
)
ORIGINAL_BUILD_STREAMS = base.build_streams


def recovery_threshold(mode: str) -> float:
    prefix = "anchor_only_reentry_"
    if not mode.startswith(prefix):
        raise ValueError("UNKNOWN_REENTRY_CONFIRMATION_MODE")
    threshold = float(mode.removeprefix(prefix))
    if not 0 <= threshold <= 0.02:
        raise ValueError("REENTRY_CONFIRMATION_OUT_OF_RANGE")
    return threshold


def build_streams(cube, development, record, models, definition):
    reentry.REENTRY_RECOVERY = recovery_threshold(definition["application_mode"])
    stop_definition = {**definition, "application_mode": "anchor_only"}
    streams, valids, exits = ORIGINAL_BUILD_STREAMS(
        cube, development, record, models, stop_definition
    )
    output = []
    for index, delay in enumerate((0, 0, 1)):
        anchor_selected, _, anchor_active = base.anchor_route(cube, models, delay)
        component_selected, _, component_active = base.component_route(cube, record, delay)
        same = (anchor_selected == component_selected) & anchor_active & component_active
        output.append(base.risk.scaled(streams[index], np.where(same, 0.775, 1.0)))
    return tuple(output), valids, exits


if __name__ == "__main__":
    base.PROPOSAL = PROPOSAL
    base.CODE_PATH = Path(__file__)
    base.CODE_DEPENDENCIES = (Path(base.__file__), Path(reentry.__file__))
    base.stopped_raw = reentry.stopped_raw
    base.build_streams = build_streams
    base.main()
