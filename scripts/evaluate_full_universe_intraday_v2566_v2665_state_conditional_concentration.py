"""Conditional exits plus monotonic-state conditional concentration control."""

from __future__ import annotations

from pathlib import Path

import evaluate_full_universe_intraday_v2166_v2265_monotonic_risk as monotonic
import evaluate_full_universe_intraday_v2266_v2365_post_entry_risk as base
import evaluate_full_universe_intraday_v2366_v2465_conditional_exit as conditional
import numpy as np

PROPOSAL = Path(__file__).resolve().parents[1] / (
    "research/proposals/full_universe_intraday_v2566_v2665_state_conditional_concentration/proposal.json"
)
ORIGINAL_BUILD_STREAMS = base.build_streams
_STATE_CACHE: dict[int, tuple[np.ndarray, dict]] = {}


def mode_parameters(mode: str) -> tuple[float, float]:
    prefix = "both_sleeves_conditional_cap_"
    if not mode.startswith(prefix) or "_q_" not in mode:
        raise ValueError("UNKNOWN_STATE_CONCENTRATION_MODE")
    cap_text, quantile_text = mode.removeprefix(prefix).split("_q_", maxsplit=1)
    cap, quantile = float(cap_text), float(quantile_text)
    if not 0 < cap <= 1 or not 0 < quantile < 1:
        raise ValueError("STATE_CONCENTRATION_PARAMETER_OUT_OF_RANGE")
    return cap, quantile


def state_score(cube, development) -> tuple[np.ndarray, np.ndarray]:
    key = id(development)
    cached = _STATE_CACHE.get(key)
    if cached is None:
        development_score, model = monotonic.fit_prediction(
            development, np.zeros(len(development.sessions))
        )
        _STATE_CACHE[key] = development_score, model
    else:
        development_score, model = cached
    score = development_score if cube is development else monotonic.predict(cube, model)
    return score, development_score


def build_streams(cube, development, record, models, definition):
    cap, quantile = mode_parameters(definition["application_mode"])
    stop_definition = {**definition, "application_mode": "both_sleeves"}
    streams, valids, exits = ORIGINAL_BUILD_STREAMS(
        cube, development, record, models, stop_definition
    )
    score, development_score = state_score(cube, development)
    train = development.masks()["train_2022_2023"] & np.isfinite(development_score)
    threshold = float(np.quantile(development_score[train], quantile))
    bad_state = ~np.isfinite(score) | (score < threshold)
    output = []
    for index, delay in enumerate((0, 0, 1)):
        anchor_selected, _, anchor_active = base.anchor_route(cube, models, delay)
        component_selected, _, component_active = base.component_route(cube, record, delay)
        same = (anchor_selected == component_selected) & anchor_active & component_active
        multiplier = np.where(same & bad_state, cap, 1.0)
        output.append(base.risk.scaled(streams[index], multiplier))
    return tuple(output), valids, exits


if __name__ == "__main__":
    base.PROPOSAL = PROPOSAL
    base.CODE_PATH = Path(__file__)
    base.CODE_DEPENDENCIES = (
        Path(base.__file__),
        Path(conditional.__file__),
        Path(monotonic.__file__),
    )
    base.stopped_raw = conditional.stopped_raw
    base.build_streams = build_streams
    base.main()
