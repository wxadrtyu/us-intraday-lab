from __future__ import annotations

import evaluate_full_universe_intraday_v8897_v8996_shrunk_sparse_gap_veto as subject


def test_shrunk_sparse_gap_contract():
    subject._configure()
    campaign = subject.sparse_veto.campaign
    assert subject.FIRST_VERSION == 8897
    assert subject.LAST_VERSION == 8996
    assert subject.PRIOR_COMPARISON_CELLS == 257_777
    assert subject.QUANTILES == (0.17, 0.18, 0.19, 0.20, 0.21)
    assert subject.ALPHAS == (100.0, 300.0)
    assert len(campaign.specifications()) == 100
