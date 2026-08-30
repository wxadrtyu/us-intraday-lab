from __future__ import annotations

import evaluate_full_universe_intraday_v8096_v8195_opening_auction_absorption as subject


def test_opening_auction_absorption_contract():
    subject._configure()
    assert subject.FIRST_VERSION == 8096
    assert subject.LAST_VERSION == 8195
    assert subject.OPENING_SLOT == (2, 11)
    assert subject.OPENING_SLOT[1] < 24
    assert subject.OPENING_QUANTILE == 0.80
    assert subject.OPENING_ALPHA == 1000.0
    assert subject.OPENING_FAMILY in subject.campaign.residual.FACTOR_SETS
    assert "trend_consistency" in subject.OPENING_FACTORS
