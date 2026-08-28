from __future__ import annotations

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest


def _module():
    sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
    import evaluate_full_universe_intraday_v349_v448_preregistered_campaign as base

    importlib.reload(base)
    name = "evaluate_full_universe_intraday_v1966_v2065_transition_campaign"
    if name in sys.modules:
        return importlib.reload(sys.modules[name])
    return importlib.import_module(name)


def test_preregistered_balance_and_comparison_budget():
    module = _module()
    specs = module.campaign.specifications()
    assert len(specs) == 100
    assert sum(s[0] == "state" for s in specs) == 50
    assert sum(s[0] == "rule" for s in specs) == 50
    assert len({repr(s) for s in specs}) == 100
    assert module.campaign.PRIOR_COMPARISON_CELLS + 50 * 5 + 50 * 48 == 113_655
    assert module.campaign.FIRST_VERSION == 1966
    assert module.campaign.LAST_VERSION == 2065


def test_transition_causal_clocks_and_missingness(monkeypatch):
    module = _module()
    opening = np.array([1.0, 3.0, 8.0, 11.0])
    prior = np.array([np.nan, 2.0, 5.0, 7.0])

    def matrix(cube, clock):
        return {"factor": opening if clock == "bar17" else prior}

    monkeypatch.setattr(module, "_base_matrix", matrix)
    np.testing.assert_allclose(
        module.transition_matrix(None, "opening_change_from_prior_close")["factor"],
        [np.nan, 1.0, 3.0, 4.0],
        equal_nan=True,
    )
    np.testing.assert_allclose(
        module.transition_matrix(None, "prior_close_change")["factor"],
        [np.nan, np.nan, 3.0, 2.0],
        equal_nan=True,
    )
    with pytest.raises(ValueError):
        module.transition_matrix(None, "same_day_close")
