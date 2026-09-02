from __future__ import annotations

import evaluate_full_universe_intraday_v9805_v10304_causal_exposure as subject


def test_exposure_grid_and_version_ranges_are_disjoint() -> None:
    assert subject.EXPOSURES == (0.0, 0.05, 0.10, 0.40, 0.60)
    ranges = [
        (subject.BASE_FIRST_VERSION + 100 * index, subject.BASE_FIRST_VERSION + 100 * index + 99)
        for index in range(len(subject.EXPOSURES))
    ]
    assert ranges[0] == (9805, 9904)
    assert ranges[-1] == (10205, 10304)
    assert all(left[1] + 1 == right[0] for left, right in zip(ranges, ranges[1:]))


def test_selected_batch_keeps_causal_repricing() -> None:
    subject._configure()
    campaign = subject.parent.parent.sparse_veto.campaign
    assert campaign.base.prior.parent._parent_streams is subject.parent._causal_parent_streams
    assert campaign.FIRST_VERSION == subject.FIRST_VERSION
    assert campaign.LAST_VERSION == subject.LAST_VERSION
    assert len(campaign.specifications()) == 100
