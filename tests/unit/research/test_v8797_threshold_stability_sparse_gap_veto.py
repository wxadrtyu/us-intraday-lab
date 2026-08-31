from __future__ import annotations

import evaluate_full_universe_intraday_v8797_v8896_threshold_stability_sparse_gap_veto as subject


def test_threshold_stability_contract():
    subject._configure()
    campaign = subject.sparse_veto.campaign
    assert subject.FIRST_VERSION == 8797
    assert subject.LAST_VERSION == 8896
    assert subject.PRIOR_COMPARISON_CELLS == 257_677
    assert subject.QUANTILES == (0.18, 0.19, 0.20, 0.21, 0.22)
    assert len(campaign.specifications()) == 100
    assert campaign.GATE_DECISION < campaign.ENTRY_BAR
