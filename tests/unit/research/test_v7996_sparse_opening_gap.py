from __future__ import annotations

import evaluate_full_universe_intraday_v7996_v8095_sparse_opening_gap as subject


def test_sparse_opening_gap_contract():
    subject._configure()
    assert subject.FIRST_VERSION == 7996
    assert subject.LAST_VERSION == 8095
    assert subject.OPENING_SLOT == (2, 11)
    assert subject.OPENING_SLOT[1] < 24
    assert subject.OPENING_QUANTILE == 0.80
    assert subject.OPENING_ALPHA == 1000.0
    assert subject.OPENING_FAMILY in subject.campaign.residual.FACTOR_SETS
    assert "gap" in subject.OPENING_FACTORS
