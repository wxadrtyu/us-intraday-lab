from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import evaluate_full_universe_intraday_v7495_v7594_last_bar_loss_veto as subject


def test_last_bar_preregistration():
    subject._configure()
    assert subject.FIRST_VERSION == 7495
    assert subject.LAST_VERSION == 7594
    assert subject.PRIOR_COMPARISON_CELLS == 256_355
    assert subject.GATE_DECISION == subject.ENTRY_BAR - 1
    assert len(subject.campaign.specifications()) == 100
    assert subject.quality.GATE_DECISION == 23
