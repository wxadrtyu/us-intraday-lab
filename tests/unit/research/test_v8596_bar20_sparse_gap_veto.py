from __future__ import annotations

import evaluate_full_universe_intraday_v8596_v8695_bar20_sparse_gap_veto as subject


def test_bar20_sparse_gap_veto_contract():
    subject._configure()
    campaign = subject.sparse_veto.campaign
    assert subject.FIRST_VERSION == 8596
    assert subject.LAST_VERSION == 8695
    assert subject.GATE_DECISION == 20
    assert subject.GATE_DECISION < subject.ENTRY_BAR
    assert campaign._route is subject.sparse_veto._sparse_gap_route
    assert campaign.GATE_DECISION == 20
    assert campaign.quality.GATE_DECISION == 20
