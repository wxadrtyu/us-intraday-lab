from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v5970_v6069_sector_flow_leadership as subject


def test_campaign_has_one_hundred_frozen_versions() -> None:
    assert subject.FIRST_VERSION == 5970
    assert subject.LAST_VERSION == 6069
    assert len(subject.FACTOR_SETS) == 10
    assert len(subject.specifications()) == 100


def test_factor_clock_is_before_modern_entry() -> None:
    assert subject.GATE_DECISION == 17
    assert subject.GATE_DECISION < subject.MODERN_ENTRY


def test_all_families_are_multifactor() -> None:
    assert all(len(factors) >= 3 for factors in subject.FACTOR_SETS.values())
