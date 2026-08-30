from __future__ import annotations

import evaluate_full_universe_intraday_v7796_v7895_liquidity_absorption as subject


def test_liquidity_absorption_contract():
    subject._configure()
    assert subject.FIRST_VERSION == 7796
    assert subject.LAST_VERSION == 7895
    assert subject.ABSORPTION_SLOT == (11, 23)
    assert subject.ABSORPTION_SLOT[1] < 24
    assert subject.ABSORPTION_QUANTILE == 0.70
    assert subject.ABSORPTION_ALPHA == 1000.0
    assert subject.ABSORPTION_FAMILY in subject.campaign.residual.FACTOR_SETS
    assert "signed_volume_imbalance" in subject.ABSORPTION_FACTORS
