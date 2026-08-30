from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import evaluate_full_universe_intraday_v7395_v7494_full_route_loss_veto as subject


def test_preregistered_grid_and_causal_boundary():
    assert subject.FIRST_VERSION == 7395
    assert subject.LAST_VERSION == 7494
    assert subject.PRIOR_COMPARISON_CELLS == 256_255
    assert len(subject.FACTOR_SETS) == 10
    assert len(subject.specifications()) == 100
    assert len(set(subject.specifications())) == 100
    assert subject.GATE_DECISION < subject.ENTRY_BAR


def test_veto_factors_cover_path_flow_and_prior_state():
    factors = {factor for family in subject.FACTOR_SETS.values() for factor in family}
    assert {"drawdown_from_high", "sector_signed_flow_breadth", "prior20_return"} <= factors
