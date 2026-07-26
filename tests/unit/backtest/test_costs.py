from dataclasses import FrozenInstanceError, replace

import pytest

from us_intraday_lab.backtest.costs import COST_SCENARIOS, CostModel

# Approved v1 conservative modeling assumptions from the Task 4 brief (2026-07-27).
# They are research parameters to calibrate against later paper fills, not broker fee claims.
APPROVED_PARAMETERS = {
    "optimistic": (0.5, 0.5, 0.0),
    "base": (1.0, 2.0, 0.0),
    "stress": (2.0, 5.0, 0.0),
}


def test_checked_in_cost_scenarios_match_approved_versioned_assumptions() -> None:
    assert set(COST_SCENARIOS) == set(APPROVED_PARAMETERS)
    for name, (
        half_spread_bps,
        slippage_bps,
        commission_per_share_usd,
    ) in APPROVED_PARAMETERS.items():
        scenario = COST_SCENARIOS[name]
        assert scenario.model_id == f"cost-{name}-1.0.0"
        assert scenario.half_spread_bps == half_spread_bps
        assert scenario.slippage_bps == slippage_bps
        assert scenario.commission_per_share_usd == commission_per_share_usd


def test_cost_scenarios_are_positive_and_strictly_ordered() -> None:
    costs = [
        COST_SCENARIOS[name].variable_cost(notional_usd=10_000.0, quantity=100)
        for name in ("optimistic", "base", "stress")
    ]

    assert costs[0] > 0
    assert costs[0] < costs[1] < costs[2]


def test_one_point_five_cost_evaluation_scales_every_variable_component() -> None:
    # The approved v1 commission is zero. Use a nonzero synthetic value only to
    # prove the scaling mechanism also covers that component if later calibrated.
    base = replace(COST_SCENARIOS["base"], commission_per_share_usd=0.02)

    scaled = base.scaled(1.5)

    assert scaled.half_spread_bps == pytest.approx(base.half_spread_bps * 1.5)
    assert scaled.slippage_bps == pytest.approx(base.slippage_bps * 1.5)
    assert scaled.commission_per_share_usd == pytest.approx(base.commission_per_share_usd * 1.5)
    assert scaled.variable_cost(10_000.0, 100) == pytest.approx(
        base.variable_cost(10_000.0, 100) * 1.5
    )


def test_no_promotable_scenario_has_all_zero_variable_costs() -> None:
    assert all(
        any(
            component > 0
            for component in (
                scenario.half_spread_bps,
                scenario.slippage_bps,
                scenario.commission_per_share_usd,
            )
        )
        for scenario in COST_SCENARIOS.values()
    )


def test_cost_model_is_frozen_and_rejects_invalid_inputs() -> None:
    scenario = COST_SCENARIOS["base"]

    with pytest.raises(FrozenInstanceError):
        scenario.slippage_bps = 0.0  # type: ignore[misc]
    with pytest.raises(ValueError, match="non-negative"):
        CostModel(
            model_id="invalid",
            half_spread_bps=-1.0,
            slippage_bps=0.0,
            commission_per_share_usd=0.0,
        )
    with pytest.raises(ValueError, match="positive"):
        scenario.variable_cost(notional_usd=0.0, quantity=1)
