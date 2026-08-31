from __future__ import annotations

import evaluate_full_universe_intraday_v8997_v9096_soft_sparse_gap_veto as subject


def test_soft_sparse_gap_contract():
    subject._configure()
    campaign = subject.sparse_veto.campaign
    assert subject.FIRST_VERSION == 8997
    assert subject.LAST_VERSION == 9096
    assert subject.LOW_EXPOSURE == 0.25
    assert len(campaign.specifications()) == 100
    assert campaign.STREAM_TRANSFORM is subject._soft_veto
