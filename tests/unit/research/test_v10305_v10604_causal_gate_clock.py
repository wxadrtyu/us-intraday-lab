from __future__ import annotations

import evaluate_full_universe_intraday_v10305_v10604_causal_gate_clock as subject


def test_gate_clock_ranges_are_disjoint() -> None:
    assert subject.GATE_DECISIONS == (5, 11, 17)
    ranges = [
        (subject.BASE_FIRST_VERSION + 100 * index, subject.BASE_FIRST_VERSION + 100 * index + 99)
        for index in range(len(subject.GATE_DECISIONS))
    ]
    assert ranges == [(10305, 10404), (10405, 10504), (10505, 10604)]


def test_selected_clock_is_causal_and_nonoverlapping() -> None:
    subject._configure()
    campaign = subject.parent.parent.sparse_veto.campaign
    assert subject.MINIMUM_ENTRY_BAR >= subject.GATE_DECISION + 1
    assert subject.MINIMUM_ENTRY_BAR >= subject.OPENING_EXIT_BAR
    assert campaign.GATE_DECISION == subject.GATE_DECISION
    assert campaign.ENTRY_BAR == subject.MINIMUM_ENTRY_BAR
    assert campaign.base.prior.parent._parent_streams is subject._clock_parent_streams
    assert len(campaign.specifications()) == 100
