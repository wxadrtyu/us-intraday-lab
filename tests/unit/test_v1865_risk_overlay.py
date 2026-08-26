from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
risk = importlib.import_module("evaluate_full_universe_intraday_v1865_v1964_risk_overlay")


def stream(value):
    return risk.prior.v12.ReturnStream(
        np.full(4, value), np.full(4, value / 2), np.ones(4, dtype=bool), np.ones(4, dtype=int)
    )


def test_one_hundred_multifactor_risk_hypotheses_and_comparison_budget():
    p = json.loads(risk.PROPOSAL.read_text())
    specs = [(f, c, r) for f, _ in p["families"] for c in p["clocks"] for r in p["policies"]]
    assert len(specs) == len(set(specs)) == 100
    assert all(len(coefficients) >= 3 for _, coefficients in p["families"])
    assert len(p["grid"]["state_quantiles"]) * len(p["grid"]["gross_budget_caps"]) * 100 == 1200
    assert p["cumulative_comparison_cells"] == 109805 + 1200


def test_cash_policy_and_budget_preserve_both_components():
    parts = ((stream(0.084), stream(0.016)),) * 3
    allowed = np.array([True, False, True, False])
    loss = np.zeros(4, dtype=bool)
    result = risk.overlay(parts, allowed, "all_cash_bad", 0.8, loss)
    for s in result:
        np.testing.assert_allclose(s.values, [0.08, 0, 0.08, 0])
        np.testing.assert_array_equal(s.active, allowed)
    anchor_cash = risk.overlay(parts, allowed, "anchor_cash_bad", 1, loss)[0]
    np.testing.assert_allclose(anchor_cash.values, [0.1, 0.016, 0.1, 0.016])


def test_invalid_state_always_fails_closed_even_for_partial_policies():
    parts = ((stream(0.084), stream(0.016)),) * 3
    for policy in json.loads(risk.PROPOSAL.read_text())["policies"]:
        output = risk.overlay(
            parts,
            np.zeros(4, dtype=bool),
            policy,
            1,
            np.zeros(4, dtype=bool),
            np.zeros(4, dtype=bool),
        )[0]
        assert not output.active.any()
        assert not output.values.any()


def test_loss_brake_never_uses_current_or_future_returns():
    values = np.array([-0.01, 0.002, 0.004, -0.02, 0.005, 0.01])
    changed = values.copy()
    changed[3:] = 0.9
    np.testing.assert_array_equal(
        risk.prior_loss_mask(values, 2)[:4], risk.prior_loss_mask(changed, 2)[:4]
    )
    assert risk.prior_loss_mask(values, 2)[2]


def test_lagged_loss_brake_needs_both_conditions():
    allowed = np.array([True, True, False, False])
    loss = np.array([False, True, False, True])
    parts = ((stream(0.084), stream(0.016)),) * 3
    result = risk.overlay(parts, allowed, "lagged_loss_brake_bad", 1, loss)[0]
    np.testing.assert_allclose(result.values, [0.1, 0.1, 0.1, 0.05])


def test_invalid_gross_budget_rejected_and_tail_loss_defined():
    with pytest.raises(ValueError, match="GROSS_BUDGET"):
        risk.overlay(
            ((stream(0.1), stream(0)),),
            np.ones(4, dtype=bool),
            "all_cash_bad",
            1.1,
            np.zeros(4, dtype=bool),
        )
    assert risk.tail_loss(np.array([-0.1] + [0.0] * 19)) == 0.1
    assert risk.tail_loss(np.ones(20)) == 0
