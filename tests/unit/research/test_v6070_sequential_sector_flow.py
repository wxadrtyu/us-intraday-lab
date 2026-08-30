from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v6070_v6169_sequential_sector_flow as subject


def test_campaign_has_one_hundred_frozen_versions() -> None:
    assert subject.FIRST_VERSION == 6070
    assert subject.LAST_VERSION == 6169
    assert len(subject.FACTOR_SETS) == 10
    assert len(subject.specifications()) == 100


def test_sleeves_are_ordered_and_nonoverlapping() -> None:
    previous_exit = -1
    for sleeve in subject.SCHEDULE:
        entry = sleeve["decision"] + 1
        assert previous_exit <= entry
        assert entry < sleeve["exit"] <= 77
        previous_exit = sleeve["exit"]


def test_all_families_are_multifactor() -> None:
    assert all(len(factors) >= 5 for factors in subject.FACTOR_SETS.values())
