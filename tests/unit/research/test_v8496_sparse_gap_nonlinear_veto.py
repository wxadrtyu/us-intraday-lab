from __future__ import annotations

import evaluate_full_universe_intraday_v8496_v8595_sparse_gap_nonlinear_veto as subject


def test_sparse_gap_nonlinear_veto_contract():
    subject._configure()
    campaign = subject.sparse_veto.campaign
    assert subject.FIRST_VERSION == 8496
    assert subject.LAST_VERSION == 8595
    assert subject.GATE_DECISION == 23
    assert subject.GATE_DECISION < subject.ENTRY_BAR
    assert campaign._route is subject.sparse_veto._sparse_gap_route
    assert campaign.FACTOR_SETS is subject.nonlinear.FACTOR_SETS
    assert campaign.sector.SectorFlowLeadershipCube is subject.nonlinear.NonlinearInteractionCube
