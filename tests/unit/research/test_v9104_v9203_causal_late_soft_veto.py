from __future__ import annotations

import evaluate_full_universe_intraday_v9104_v9203_causal_late_soft_veto as subject


def test_causal_late_soft_veto_contract():
    subject._configure()
    campaign = subject.sparse_veto.campaign
    assert subject.FIRST_VERSION == 9104
    assert subject.LAST_VERSION == 9203
    assert subject.GATE_DECISION < subject.ENTRY_BAR
    assert subject.LOW_EXPOSURE == 0.25
    assert campaign._route is subject._late_only_route
    assert campaign.STREAM_TRANSFORM is subject._soft_veto
    assert len(campaign.specifications()) == 100
