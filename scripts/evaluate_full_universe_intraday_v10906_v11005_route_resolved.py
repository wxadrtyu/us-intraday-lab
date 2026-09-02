"""v10906-v11005 fully route-resolved successor to revoked v10824.

All parent sleeves, including wide-fill components, enter no earlier than bar
24.  The modern/fallback route is therefore known at bar 23 before any late
position can exist.  The fixed opening sleeve still exits at bar 11.
"""

from __future__ import annotations

import evaluate_full_universe_intraday_v9605_v9704_causal_repriced_v9292 as repriced
import evaluate_full_universe_intraday_v10805_v10904_bar5_and_boundary as boundary

FIRST_VERSION = 10906
LAST_VERSION = 11005
PRIOR_COMPARISON_CELLS = 285_683
ROUTE_DECISION_BAR = 23
MINIMUM_ENTRY_BAR = ROUTE_DECISION_BAR + 1


def _route_resolved_parent_streams(cube, frozen_parent: dict, model):
    raw = (
        repriced._repriced_sleeve(
            cube, model, repriced.v34.STANDARD_COST, 0, MINIMUM_ENTRY_BAR
        ),
        repriced._repriced_sleeve(
            cube, model, repriced.v34.STRESS_COST, 0, MINIMUM_ENTRY_BAR
        ),
        repriced._repriced_sleeve(
            cube, model, repriced.v34.STANDARD_COST, 1, MINIMUM_ENTRY_BAR
        ),
    )
    definition = frozen_parent["definition"]
    exposure = repriced.v42._exposure(
        raw[0].values,
        int(definition["lookback"]),
        float(definition["target_volatility"]),
        float(definition["minimum_exposure"]),
    )
    return tuple(repriced.v42._scaled(stream, exposure) for stream in raw)


def _configure() -> None:
    boundary._configure()
    campaign = boundary.logical.clock.parent.parent.sparse_veto.campaign
    campaign.base.prior.parent._parent_streams = _route_resolved_parent_streams
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.MECHANISM = "route_resolved_bar24_fill_plus_bar5_logical_soft_gate"


if __name__ == "__main__":
    _configure()
    boundary.logical.clock.parent.parent.sparse_veto.campaign.main()
