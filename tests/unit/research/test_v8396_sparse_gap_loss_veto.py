from __future__ import annotations

import evaluate_full_universe_intraday_v8396_v8495_sparse_gap_loss_veto as subject


def test_sparse_gap_loss_veto_contract():
    subject._configure()
    assert subject.FIRST_VERSION == 8396
    assert subject.LAST_VERSION == 8495
    assert subject.GATE_DECISION == 23
    assert subject.GATE_DECISION < subject.ENTRY_BAR
    assert subject.FROZEN_ROUTE_VERSION == 8055
    assert subject.FROZEN_STATE_QUANTILE == 0.80
    assert subject.campaign._route is subject._sparse_gap_route
    assert subject.campaign.quality.GATE_DECISION == 23
