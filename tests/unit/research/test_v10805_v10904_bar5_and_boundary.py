from __future__ import annotations

import evaluate_full_universe_intraday_v10805_v10904_bar5_and_boundary as subject


def test_boundary_extension_preregistration() -> None:
    assert subject.FIRST_VERSION == 10805
    assert subject.LAST_VERSION == 10904
    assert len(subject.PAIR_SPECS) == 5
    assert all(spec[2] == "and" for spec in subject.PAIR_SPECS.values())
    assert len(subject.QUANTILES) * len(subject.ALPHAS) * len(subject.PAIR_SPECS) == 100


def test_boundary_extension_keeps_causal_execution() -> None:
    subject._configure()
    campaign = subject.logical.clock.parent.parent.sparse_veto.campaign
    assert campaign.GATE_DECISION == 5
    assert campaign.ENTRY_BAR == 11
    assert len(campaign.specifications()) == 100
