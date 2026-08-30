from __future__ import annotations

import evaluate_full_universe_intraday_v8196_v8295_dual_intraday_sleeve as subject


def test_dual_intraday_sleeve_contract():
    subject._configure()
    assert subject.FIRST_VERSION == 8196
    assert subject.LAST_VERSION == 8295
    assert subject.OPENING_SLOT == (2, 11)
    assert subject.PREROUTE_SLOT == (11, 23)
    assert subject.OPENING_SLOT[1] < subject.PREROUTE_SLOT[0] + 1
    assert subject.PREROUTE_SLOT[1] < 24
    assert subject.SCORE_QUANTILE == 0.80
    assert subject.foundation.campaign.EXTRA_COMPONENT_BUILDER is subject._dual_components
    assert subject.OPENING_FAMILY in subject.residual.FACTOR_SETS
    assert subject.PREROUTE_FAMILY in subject.residual.FACTOR_SETS
