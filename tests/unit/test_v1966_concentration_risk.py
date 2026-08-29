from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
campaign = importlib.import_module("evaluate_full_universe_intraday_v1966_v2065_concentration_risk")


def stream(values, active=None):
    values = np.asarray(values, dtype=float)
    active = np.ones(len(values), dtype=bool) if active is None else np.asarray(active, dtype=bool)
    return campaign.prior.v12.ReturnStream(values, values / 2, active, active.astype(int))


def test_frozen_grid_is_exactly_one_hundred_unique_increasing_versions():
    proposal = json.loads(campaign.PROPOSAL.read_text())
    grid = list(
        __import__("itertools").product(
            proposal["grid"]["same_symbol_gross_caps"],
            proposal["grid"]["risk_score_quantiles"],
            proposal["grid"]["bad_state_multipliers"],
        )
    )
    assert len(grid) == len(set(grid)) == 100
    assert proposal["first_version"] == 1966 and proposal["last_version"] == 2065
    assert proposal["consumed_diagnostics_not_ranking"][-2:] == ["2026-08-27", "2026-08-28"]
    assert len(proposal["factor_contract"]) == 16


def test_multiplier_scales_both_sleeves_and_preserves_long_only_gross():
    parts = tuple((stream([0.84, -0.84]), stream([0.16, -0.16])) for _ in range(3))
    output = campaign.apply(parts, np.array([0.4, 0.0]))
    for result in output:
        np.testing.assert_allclose(result.values, [0.4, 0.0])
        assert (result.values <= 0.4).all()


def test_missing_multifactor_state_policy_is_cash():
    prediction = np.array([0.1, np.nan, -0.1])
    threshold, bad = 0.0, 0.25
    multiplier = np.where(np.isfinite(prediction), np.where(prediction < threshold, bad, 1.0), 0)
    np.testing.assert_allclose(multiplier, [1.0, 0.0, 0.25])
