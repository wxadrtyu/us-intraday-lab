from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v5870_v5969_nonlinear_meta_gate as subject


def test_campaign_has_one_hundred_frozen_versions() -> None:
    assert subject.FIRST_VERSION == 5870
    assert subject.LAST_VERSION == 5969
    assert len(subject.specifications()) == 100


def test_meta_clock_is_before_modern_entry() -> None:
    assert subject.GATE_DECISION == 17
    assert subject.GATE_DECISION < subject.MODERN_ENTRY
