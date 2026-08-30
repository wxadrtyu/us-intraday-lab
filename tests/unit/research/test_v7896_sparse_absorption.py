from __future__ import annotations

import evaluate_full_universe_intraday_v7896_v7995_sparse_absorption as subject


def test_sparse_absorption_contract():
    subject._configure()
    assert subject.FIRST_VERSION == 7896
    assert subject.LAST_VERSION == 7995
    assert subject.ABSORPTION_SLOT == (11, 23)
    assert subject.ABSORPTION_SLOT[1] < 24
    assert subject.ABSORPTION_QUANTILE == 0.80
    assert subject.ABSORPTION_ALPHA == 1000.0
    assert subject.ABSORPTION_FAMILY in subject.campaign.residual.FACTOR_SETS
    assert "volume_acceleration" in subject.ABSORPTION_FACTORS
