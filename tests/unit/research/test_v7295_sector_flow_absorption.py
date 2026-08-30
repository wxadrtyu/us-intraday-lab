from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import evaluate_full_universe_intraday_v7295_v7394_sector_flow_absorption as subject


def test_preregistration_grid_and_causal_timing():
    specs = subject.specifications()
    assert subject.FIRST_VERSION == 7295
    assert subject.LAST_VERSION == 7394
    assert subject.PRIOR_COMPARISON_CELLS == 256_155
    assert len(subject.FACTOR_SETS) == 10
    assert len(specs) == 100
    assert len(set(specs)) == 100
    assert subject.GATE_DECISION < subject.MODERN_ENTRY


def test_factor_contract_combines_path_and_sector_flow():
    all_factors = {factor for factors in subject.FACTOR_SETS.values() for factor in factors}
    assert "drawdown_from_high" in all_factors
    assert "return_acceleration" in all_factors
    assert "sector_signed_flow_breadth" in all_factors
    assert "sector_volatility_contraction" in all_factors
    assert "growth_minus_defensive_flow" in all_factors
