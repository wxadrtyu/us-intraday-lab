from __future__ import annotations

import evaluate_full_universe_intraday_v6495_v6594_sequential_sector_flow as subject


def test_sequential_sector_flow_version_contract():
    assert subject.FIRST_VERSION == 6495
    assert subject.LAST_VERSION == 6594
    assert len(subject.campaign.specifications()) == 100
    intervals = [(item["decision"], item["exit"]) for item in subject.campaign.SCHEDULE]
    assert all(left[1] < right[0] for left, right in zip(intervals, intervals[1:], strict=True))
