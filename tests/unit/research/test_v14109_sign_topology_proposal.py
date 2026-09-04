from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v14109_v14208_sign_topology_alpha as campaign


def test_v14109_sign_topology_campaign_is_frozen_before_implementation() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v14109_v14208_sign_topology_alpha/proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == 14109
    assert proposal["last_version"] == 14208
    assert proposal["planned_versions"] == 100
    assert proposal["planned_parameter_cells"] == 1000
    assert proposal["prior_comparison_cells"] == 335_183
    assert proposal["cumulative_comparison_cells"] == 336_183
    assert proposal["diagnostics_not_selection"] == [
        "historical_2018_2020",
        "consumed_2026q1",
        "consumed_2026_all",
    ]
    assert proposal["execution"] == {
        "long_only": True,
        "gross_limit": 1.0,
        "overnight": False,
    }
    assert len(campaign.REPRESENTATIONS) * len(campaign.SCHEDULES) == 100
    assert all(
        decision >= window + aggregation - 1
        for decision, _exit in campaign.SCHEDULES
        for _source, aggregation, window in campaign.REPRESENTATIONS.values()
    )


def test_sign_topology_matrix_cannot_see_bars_after_decision() -> None:
    class Cube:
        pass

    cube = Cube()
    rng = np.random.default_rng(11)
    cube.bar_return = rng.normal(0, 0.01, size=(7, 78, 16))
    model = campaign.SignTopologyModel(
        "raw_short",
        campaign.FACTORS,
        11,
        41,
        np.empty(0),
        np.empty(0),
        np.empty(0),
        "raw",
        1,
        5,
    )
    before = campaign._sign_topology_matrix(cube, model).copy()
    campaign._MATRIX_CACHE.clear()
    cube.bar_return[:, 12:, :] = 999.0
    after = campaign._sign_topology_matrix(cube, model)
    np.testing.assert_allclose(before, after)


def test_campaign_configuration_is_long_only_single_asset() -> None:
    campaign._configure()
    assert tuple(campaign.base.ASSETS) == (3, 4)
    assert campaign.base.TOP_K == (1,)
    assert campaign.base.MECHANISM == "causal_intraday_return_sign_topology_alpha"
