from __future__ import annotations

import evaluate_full_universe_intraday_v6295_v6394_wide_diversification as subject


def test_wide_diversification_preregistration():
    assert subject.campaign.FIRST_VERSION == 6295
    assert subject.campaign.LAST_VERSION == 6394
    assert subject.campaign.COUNTS == (8, 10, 12, 16, 20)
    assert len(subject.campaign.specifications()) == 100
