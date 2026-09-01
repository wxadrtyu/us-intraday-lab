from __future__ import annotations

import evaluate_full_universe_intraday_v9204_v9303_causal_opening_late_soft_veto as subject


def test_causal_opening_late_contract():
    subject._configure()
    campaign = subject.sparse_veto.campaign
    assert subject.FIRST_VERSION == 9204
    assert subject.LAST_VERSION == 9303
    assert subject.OPENING_DECISION < subject.OPENING_ENTRY <= subject.OPENING_EXIT
    assert subject.OPENING_EXIT < subject.LATE_GATE_DECISION < subject.LATE_ENTRY
    assert campaign._route is subject._causal_route
    assert campaign.STREAM_TRANSFORM is subject._late_soft_veto_plus_fixed_opening
    assert len(campaign.specifications()) == 100
