"""Five preregistered 100-cell causal residual-exposure batches.

Set ``V9292_EXPOSURE_INDEX`` to 0..4 before launch. Each process owns a
disjoint 100-version range and writes its own atomic result file.
"""

from __future__ import annotations

import os

import evaluate_full_universe_intraday_v9605_v9704_causal_repriced_v9292 as parent
import numpy as np


EXPOSURES = (0.0, 0.05, 0.10, 0.40, 0.60)
BASE_FIRST_VERSION = 9805
BASE_PRIOR_COMPARISON_CELLS = 284_583
EXPOSURE_INDEX = int(os.environ.get("V9292_EXPOSURE_INDEX", "0"))
if not 0 <= EXPOSURE_INDEX < len(EXPOSURES):
    raise RuntimeError("V9292_EXPOSURE_INDEX_OUT_OF_RANGE")
LOW_EXPOSURE = EXPOSURES[EXPOSURE_INDEX]
FIRST_VERSION = BASE_FIRST_VERSION + 100 * EXPOSURE_INDEX
LAST_VERSION = FIRST_VERSION + 99
PRIOR_COMPARISON_CELLS = BASE_PRIOR_COMPARISON_CELLS + 100 * EXPOSURE_INDEX


def _exposure_transform(stream, allowed):
    opening = parent.parent._opening_by_late_stream.get(id(stream))
    if opening is None:
        raise RuntimeError("CAUSAL_OPENING_STREAM_NOT_REGISTERED")
    exposure = np.where(allowed, 1.0, LOW_EXPOSURE)
    route_active = stream.active & (exposure > 0)
    return parent.v34.v12.ReturnStream(
        stream.values * exposure + opening.values,
        stream.benchmark * exposure + opening.benchmark,
        route_active | opening.active,
        np.where(route_active, stream.component_trades, 0) + opening.component_trades,
    )


def _configure() -> None:
    parent._configure()
    campaign = parent.parent.sparse_veto.campaign
    campaign.FIRST_VERSION = FIRST_VERSION
    campaign.LAST_VERSION = LAST_VERSION
    campaign.PRIOR_COMPARISON_CELLS = PRIOR_COMPARISON_CELLS
    campaign.STREAM_TRANSFORM = _exposure_transform
    campaign.MECHANISM = f"causal_repriced_v9292_residual_exposure_{LOW_EXPOSURE:.2f}"


if __name__ == "__main__":
    _configure()
    parent.parent.sparse_veto.campaign.main()
