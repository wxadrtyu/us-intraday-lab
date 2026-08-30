from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v5670_v5769_modern_quality_gate as subject


def test_campaign_has_one_hundred_frozen_versions() -> None:
    assert subject.FIRST_VERSION == 5670
    assert subject.LAST_VERSION == 5769
    assert len(subject.specifications()) == 100


def test_modern_gate_is_causal() -> None:
    assert subject.GATE_DECISION == 17
    assert subject.MODERN_ENTRY == 24
    assert subject.GATE_DECISION < subject.MODERN_ENTRY
