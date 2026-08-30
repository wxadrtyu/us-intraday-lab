from __future__ import annotations

import importlib
import sys
from pathlib import Path


def test_v5995_preregistered_early_clock_and_one_hundred_versions():
    sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))
    module = importlib.import_module(
        "evaluate_full_universe_intraday_v5995_v6094_nonlinear_early_state"
    )
    module._configure()
    c = module.campaign
    assert (c.FIRST_VERSION, c.LAST_VERSION) == (5995, 6094)
    assert c.GATE_DECISION == 2
    assert len(c.specifications()) == 100
    assert len({repr(x) for x in c.specifications()}) == 100
    assert c.PRIOR_COMPARISON_CELLS + len(c.specifications()) == 254955
