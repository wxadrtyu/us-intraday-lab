from __future__ import annotations

import evaluate_full_universe_intraday_v6295_v6394_wide_diversification as subject


def test_wide_diversification_preregistration():
    assert subject.campaign.FIRST_VERSION == 6295
    assert subject.campaign.LAST_VERSION == 6394
    assert subject.campaign.COUNTS == (8, 10, 12, 16, 20)
    assert len(subject.campaign.specifications()) == 100


def test_nested_selection_cache_reuses_longest_path(monkeypatch):
    calls = []

    def fake(cube, parent_ids, streams, count, penalty, weighting):
        calls.append(count)
        return tuple(parent_ids[:count])

    monkeypatch.setattr(subject, "_original_greedy", fake)
    subject._selection_cache.clear()
    ids = tuple(str(index) for index in range(25))
    assert len(subject._cached_greedy(None, ids, {}, 8, 0.5, "equal")) == 8
    assert len(subject._cached_greedy(None, ids, {}, 16, 0.5, "equal")) == 16
    assert calls == [20]
