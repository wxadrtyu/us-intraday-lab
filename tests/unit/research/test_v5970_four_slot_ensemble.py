from __future__ import annotations

import importlib
import sys
from pathlib import Path

import numpy as np


def test_v5970_preregistration_and_nonoverlap():
    sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))
    module = importlib.import_module(
        "evaluate_full_universe_intraday_v5970_v5994_four_slot_ensemble"
    )
    assert (module.FIRST_VERSION, module.LAST_VERSION) == (5970, 5994)
    assert len(module.specifications()) == 25
    assert len(set(module.specifications())) == 25
    assert len(module.QUANTILES) * len(module.TARGETS) * len(module.specifications()) == 250
    assert all(
        left[1] < right[0] for left, right in zip(module.SLOTS, module.SLOTS[1:])
    )


def test_sum_streams_accumulates_sequential_pnl_and_trade_count():
    sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))
    module = importlib.import_module(
        "evaluate_full_universe_intraday_v5970_v5994_four_slot_ensemble"
    )
    cls = module.v34.v12.ReturnStream
    a = cls(np.array([0.1, 0.0]), np.array([0.01, 0.0]), np.array([True, False]), np.array([1, 0]))
    b = cls(np.array([0.2, 0.3]), np.array([0.02, 0.03]), np.array([True, True]), np.array([1, 1]))
    out = module._sum_streams([a, b])
    np.testing.assert_allclose(out.values, [0.3, 0.3])
    np.testing.assert_array_equal(out.component_trades, [2, 1])
    np.testing.assert_array_equal(out.active, [True, True])
