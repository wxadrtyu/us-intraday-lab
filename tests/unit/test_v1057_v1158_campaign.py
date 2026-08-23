from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import numpy as np


def _campaign():
    scripts = Path(__file__).parents[2] / "scripts"
    sys.path.insert(0, str(scripts))
    return importlib.import_module(
        "evaluate_full_universe_intraday_v753_v852_dual_component_routing"
    )


def test_blocked_component_weight_returns_to_anchor() -> None:
    campaign = _campaign()
    stream = campaign.prior.v12.ReturnStream
    anchor = stream(
        np.array([0.01, 0.02]),
        np.array([0.001, 0.002]),
        np.array([True, True]),
        np.array([1, 1]),
    )
    component = stream(
        np.array([0.0, 0.05]),
        np.array([0.0, 0.004]),
        np.array([False, True]),
        np.array([0, 1]),
    )
    empty = stream(
        np.zeros(2),
        np.zeros(2),
        np.array([False, False]),
        np.zeros(2, dtype=int),
    )
    campaign.REALLOCATE_TO_ANCHOR_WHEN_BLOCKED = True
    try:
        result = campaign._blend(
            anchor,
            empty,
            component,
            total_weight=0.1,
            v247_share=0.0,
            allowed=np.array([False, True]),
        )
    finally:
        campaign.REALLOCATE_TO_ANCHOR_WHEN_BLOCKED = False
    np.testing.assert_allclose(result.values, np.array([0.01, 0.023]))
    np.testing.assert_allclose(result.benchmark, np.array([0.001, 0.0022]))


def test_v1057_campaign_proposal_freezes_one_hundred_versions() -> None:
    path = (
        Path(__file__).parents[2]
        / "research"
        / "proposals"
        / "full_universe_intraday_v1057_v1156"
        / "proposal.json"
    )
    proposal = json.loads(path.read_text(encoding="utf-8"))
    assert proposal["version_range"] == [1057, 1156]
    assert proposal["version_count"] == 100
    assert proposal["planned_cells"] == 400
    assert proposal["cumulative_comparison_cells"] == 67_555
