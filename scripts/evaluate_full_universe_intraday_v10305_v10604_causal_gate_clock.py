"""Three preregistered causal gate-clock batches for the v9292 successor.

Set ``V9292_GATE_CLOCK_INDEX`` to 0..2. Route entry occurs only after the gate
and never overlaps the fixed opening sleeve, which exits at bar 11.
"""

from __future__ import annotations

import os

import evaluate_full_universe_intraday_v9605_v9704_causal_repriced_v9292 as parent


GATE_DECISIONS = (5, 11, 17)
OPENING_EXIT_BAR = 11
BASE_FIRST_VERSION = 10305
BASE_PRIOR_COMPARISON_CELLS = 285_083
GATE_CLOCK_INDEX = int(os.environ.get("V9292_GATE_CLOCK_INDEX", "0"))
if not 0 <= GATE_CLOCK_INDEX < len(GATE_DECISIONS):
    raise RuntimeError("V9292_GATE_CLOCK_INDEX_OUT_OF_RANGE")
GATE_DECISION = GATE_DECISIONS[GATE_CLOCK_INDEX]
MINIMUM_ENTRY_BAR = max(GATE_DECISION + 1, OPENING_EXIT_BAR)
FIRST_VERSION = BASE_FIRST_VERSION + 100 * GATE_CLOCK_INDEX
LAST_VERSION = FIRST_VERSION + 99
PRIOR_COMPARISON_CELLS = BASE_PRIOR_COMPARISON_CELLS + 100 * GATE_CLOCK_INDEX


def _clock_parent_streams(cube, frozen_parent: dict, model):
    raw = (
        parent._repriced_sleeve(
            cube, model, parent.v34.STANDARD_COST, 0, MINIMUM_ENTRY_BAR
        ),
        parent._repriced_sleeve(
            cube, model, parent.v34.STRESS_COST, 0, MINIMUM_ENTRY_BAR
        ),
        parent._repriced_sleeve(
            cube, model, parent.v34.STANDARD_COST, 1, MINIMUM_ENTRY_BAR
        ),
    )
    definition = frozen_parent["definition"]
    exposure = parent.v42._exposure(
        raw[0].values,
        int(definition["lookback"]),
        float(definition["target_volatility"]),
        float(definition["minimum_exposure"]),
    )
    return tuple(parent.v42._scaled(stream, exposure) for stream in raw)


def _configure() -> None:
    parent._configure()
    campaign = parent.parent.sparse_veto.campaign
    campaign.base.prior.parent._parent_streams = _clock_parent_streams
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.GATE_DECISION = GATE_DECISION
    campaign.ENTRY_BAR = MINIMUM_ENTRY_BAR
    campaign.quality.GATE_DECISION = GATE_DECISION
    campaign.MECHANISM = (
        f"causal_repriced_v9292_gate_{GATE_DECISION}_entry_{MINIMUM_ENTRY_BAR}"
    )


if __name__ == "__main__":
    _configure()
    parent.parent.sparse_veto.campaign.main()
