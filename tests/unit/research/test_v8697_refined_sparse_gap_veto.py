from __future__ import annotations

import evaluate_full_universe_intraday_v8697_v8796_refined_sparse_gap_veto as subject


def test_refined_sparse_gap_veto_contract():
    subject._configure()
    campaign = subject.sparse_veto.campaign
    assert subject.FIRST_VERSION == 8697
    assert subject.LAST_VERSION == 8796
    assert subject.PRIOR_COMPARISON_CELLS == 257_577
    assert subject.QUANTILES == (0.10, 0.15, 0.20, 0.25, 0.30)
    assert subject.ALPHAS == (30.0, 100.0)
    assert len(campaign.specifications()) == 100
    assert campaign.GATE_DECISION < campaign.ENTRY_BAR
