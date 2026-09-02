from __future__ import annotations

import numpy as np
import pytest

from us_intraday_lab.paper.v10824 import assemble_forward_plan, routed_anchor


def test_routed_anchor_selects_modern_transfer_and_fallback() -> None:
    values, active = routed_anchor(
        modern_state=np.array([True, False, False]),
        transfer_allowed=np.array([False, True, False]),
        modern_values=np.array([1.0, 1.0, 1.0]),
        modern_active=np.array([True, True, True]),
        transfer_values=np.array([2.0, 2.0, 2.0]),
        transfer_active=np.array([True, True, True]),
        fallback_values=np.array([3.0, 3.0, 3.0]),
        fallback_active=np.array([True, False, True]),
    )
    np.testing.assert_array_equal(values, [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(active, [True, True, True])


def test_forward_plan_uses_disjoint_fill_then_soft_exposure() -> None:
    plan = assemble_forward_plan(
        opening_values=np.array([0.01, 0.0, 0.02]),
        opening_active=np.array([True, False, True]),
        anchor_values=np.array([0.10, 0.0, 0.0]),
        anchor_active=np.array([True, False, False]),
        fill_values=np.array([0.20, 0.20, 0.20]),
        fill_active=np.array([True, True, True]),
        fill_allowed=np.array([True, True, False]),
        outer_allowed=np.array([False, True, True]),
    )
    np.testing.assert_allclose(plan.values, [0.035, 0.20, 0.02])
    np.testing.assert_array_equal(plan.active, [True, True, True])
    np.testing.assert_array_equal(plan.late_source, [1, 2, 0])
    np.testing.assert_allclose(plan.late_exposure, [0.25, 1.0, 1.0])


def test_forward_plan_fails_closed_on_bad_shapes_or_exposure() -> None:
    args = {
        "opening_values": np.zeros(2),
        "opening_active": np.zeros(2, dtype=bool),
        "anchor_values": np.zeros(2),
        "anchor_active": np.zeros(2, dtype=bool),
        "fill_values": np.zeros(2),
        "fill_active": np.zeros(2, dtype=bool),
        "fill_allowed": np.zeros(2, dtype=bool),
        "outer_allowed": np.zeros(2, dtype=bool),
    }
    with pytest.raises(ValueError, match="LOW_EXPOSURE"):
        assemble_forward_plan(**args, low_exposure=1.1)
    args["fill_values"] = np.zeros(3)
    with pytest.raises(ValueError, match="SHAPE_MISMATCH"):
        assemble_forward_plan(**args)
