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


def test_stress_floor_rank_prioritizes_the_worst_oos_scenario() -> None:
    campaign = _campaign()

    def observation(oos_return: float, mdd: float, ir: float) -> dict:
        return {
            "development_oos_2024_2025": {
                "annualized_return": oos_return,
                "max_drawdown": mdd,
                "information_ratio": ir,
            },
            "train_2022_2023": {"annualized_return": 0.10},
            "2024": {"annualized_return": 0.12},
            "2025": {"annualized_return": 0.90},
        }

    uneven = (
        observation(0.70, 0.10, 1.5),
        observation(0.55, 0.11, 1.3),
        observation(0.60, 0.12, 1.4),
    )
    robust = (
        observation(0.64, 0.11, 1.4),
        observation(0.58, 0.12, 1.35),
        observation(0.59, 0.13, 1.38),
    )
    campaign.RANK_MODE = "stress_floor"
    try:
        assert campaign._rank(robust) > campaign._rank(uneven)
    finally:
        campaign.RANK_MODE = "legacy"


def test_v1159_campaign_proposal_freezes_stress_ranking_before_2026() -> None:
    path = (
        Path(__file__).parents[2]
        / "research"
        / "proposals"
        / "full_universe_intraday_v1159_v1258"
        / "proposal.json"
    )
    proposal = json.loads(path.read_text(encoding="utf-8"))
    assert proposal["version_range"] == [1159, 1258]
    assert proposal["planned_cells"] == 400
    assert proposal["cumulative_comparison_cells"] == 67_955
    assert "consumed 2026" in proposal["ranking_boundary"]
