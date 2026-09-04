from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v14209_v14308_intrabar_rejection_alpha as campaign


def test_v14209_intrabar_rejection_campaign_is_frozen_before_implementation() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v14209_v14308_intrabar_rejection_alpha/proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == 14209
    assert proposal["last_version"] == 14308
    assert proposal["planned_versions"] == 100
    assert proposal["planned_parameter_cells"] == 1000
    assert proposal["prior_comparison_cells"] == 336_183
    assert proposal["cumulative_comparison_cells"] == 337_183
    assert proposal["execution"] == {
        "long_only": True,
        "gross_limit": 1.0,
        "overnight": False,
        "entry": "next_5_minute_bar_open",
    }
    assert len(campaign.REPRESENTATIONS) * len(campaign.SCHEDULES) == 100


def test_wick_matrix_cannot_see_bars_after_decision() -> None:
    class Cube:
        pass

    cube = Cube()
    rng = np.random.default_rng(29)
    cube.opens = rng.uniform(90, 110, size=(5, 78, 16))
    movement = rng.normal(0, 0.2, size=(5, 78, 16))
    cube.closes = cube.opens + movement
    cube.highs = np.maximum(cube.opens, cube.closes) + 0.1
    cube.lows = np.minimum(cube.opens, cube.closes) - 0.1
    model = campaign.WickModel(
        "medium_equal_rejection",
        campaign.FACTORS,
        11,
        41,
        np.empty(0),
        np.empty(0),
        np.empty(0),
        "equal",
        5,
    )
    before = campaign._wick_matrix(cube, model).copy()
    campaign._MATRIX_CACHE.clear()
    cube.opens[:, 12:, :] = 999.0
    cube.closes[:, 12:, :] = 1000.0
    cube.highs[:, 12:, :] = 1001.0
    cube.lows[:, 12:, :] = 998.0
    after = campaign._wick_matrix(cube, model)
    np.testing.assert_allclose(before, after)


def test_campaign_configuration_is_long_only_single_asset() -> None:
    campaign._configure()
    assert tuple(campaign.base.ASSETS) == (3, 4)
    assert campaign.base.TOP_K == (1,)
    assert campaign.base.MECHANISM == "causal_completed_candle_rejection_alpha"
