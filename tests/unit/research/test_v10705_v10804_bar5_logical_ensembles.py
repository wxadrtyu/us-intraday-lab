from __future__ import annotations

import evaluate_full_universe_intraday_v10705_v10804_bar5_logical_ensembles as subject


def test_logical_ensemble_preregistration() -> None:
    assert subject.FIRST_VERSION == 10705
    assert subject.LAST_VERSION == 10804
    assert len(subject.PAIR_SPECS) == 10
    assert {spec[2] for spec in subject.PAIR_SPECS.values()} == {"and", "or"}


def test_logical_ensembles_keep_bar5_causal_execution() -> None:
    subject._configure()
    campaign = subject.clock.parent.parent.sparse_veto.campaign
    assert campaign.GATE_DECISION == 5
    assert campaign.ENTRY_BAR == 11
    assert campaign.base.prior.parent._parent_streams is subject.clock._clock_parent_streams
    assert len(campaign.specifications()) == 100
