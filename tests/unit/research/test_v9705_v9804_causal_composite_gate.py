from __future__ import annotations

import evaluate_full_universe_intraday_v9705_v9804_causal_composite_gate as subject


def test_preregistered_composite_contract() -> None:
    assert subject.FIRST_VERSION == 9705
    assert subject.LAST_VERSION == 9804
    assert len(subject.FACTOR_SETS) == 10
    assert len(set(subject.FACTOR_SETS)) == 10
    assert all(len(factors) >= 5 for factors in subject.FACTOR_SETS.values())


def test_composite_keeps_causal_repricing() -> None:
    subject._configure()
    campaign = subject.parent.parent.sparse_veto.campaign
    assert campaign.base.prior.parent._parent_streams is subject.parent._causal_parent_streams
    assert campaign.GATE_DECISION == 23
    assert campaign.ENTRY_BAR == 24
    assert len(campaign.specifications()) == 100
