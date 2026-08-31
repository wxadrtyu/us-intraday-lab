from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))

import evaluate_full_universe_intraday_v7595_v7694_nonlinear_loss_veto as subject


def test_nonlinear_preregistration():
    subject._configure()
    assert subject.FIRST_VERSION == 7595
    assert subject.LAST_VERSION == 7694
    assert subject.PRIOR_COMPARISON_CELLS == 256_455
    assert len(subject.FACTOR_SETS) == 10
    assert len(subject.campaign.specifications()) == 100
    assert subject.GATE_DECISION < subject.ENTRY_BAR
    assert subject.sector.SectorFlowLeadershipCube is subject.NonlinearInteractionCube
