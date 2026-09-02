from __future__ import annotations

import evaluate_full_universe_intraday_v10605_v10704_bar5_development_composites as subject


def test_bar5_composite_preregistration() -> None:
    assert subject.FIRST_VERSION == 10605
    assert subject.LAST_VERSION == 10704
    assert len(subject.FACTOR_SETS) == 10
    assert all(len(factors) >= 5 for factors in subject.FACTOR_SETS.values())


def test_composites_keep_bar5_causal_execution() -> None:
    subject._configure()
    campaign = subject.clock.parent.parent.sparse_veto.campaign
    assert campaign.GATE_DECISION == 5
    assert campaign.ENTRY_BAR == 11
    assert campaign.base.prior.parent._parent_streams is subject.clock._clock_parent_streams
    assert len(campaign.specifications()) == 100
