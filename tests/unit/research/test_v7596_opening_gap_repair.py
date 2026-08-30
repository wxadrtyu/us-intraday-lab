from __future__ import annotations

import evaluate_full_universe_intraday_v7596_v7695_opening_gap_repair as subject


def test_short_gap_repair_contract():
    subject._configure()
    assert subject.FIRST_VERSION == 7596
    assert subject.LAST_VERSION == 7695
    assert subject.OPENING_SLOT == (2, 11)
    assert subject.OPENING_SLOT[1] < 24
    assert subject.OPENING_FAMILY == "short_gap_reversal"
    assert subject.OPENING_FAMILY in subject.campaign.residual.FACTOR_SETS
    assert "gap" in subject.OPENING_FACTORS
