from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v4470_v4569_early_quality_gate as subject


def test_campaign_has_one_hundred_frozen_versions() -> None:
    assert subject.FIRST_VERSION == 4470
    assert subject.LAST_VERSION == 4569
    assert len(subject.specifications()) == 100


def test_gate_clock_precedes_transfer_entry() -> None:
    assert subject.GATE_DECISION == 2
    assert subject.TRANSFER_ENTRY == 3
    assert subject.GATE_DECISION < subject.TRANSFER_ENTRY
