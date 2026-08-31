from __future__ import annotations

import evaluate_full_universe_intraday_v8696_consensus_veto as subject


def test_consensus_veto_contract():
    original = {
        "version": subject.ensemble.VERSION,
        "prior": subject.ensemble.PRIOR_COMPARISON_CELLS,
        "selection": subject.ensemble.SELECTION_VERSION_RANGE,
        "combiner": subject.ensemble.COMPONENT_COMBINER,
        "null": subject.ensemble.NATIVE_NULL,
        "mechanism": subject.ensemble.MECHANISM,
        "weight": subject.ensemble.COMPONENT_WEIGHT,
    }
    try:
        subject._configure()
        assert subject.VERSION == 8696
        assert subject.SELECTION_VERSION_RANGE == [8396, 8495]
        assert subject.CONSENSUS_SHARE == 0.60
        assert subject.ensemble.COMPONENT_COMBINER is subject._consensus
        assert subject.ensemble.NATIVE_NULL is subject._consensus_native_null
        assert subject.sparse_veto.campaign._route is subject.sparse_veto._sparse_gap_route
    finally:
        subject.ensemble.VERSION = original["version"]
        subject.ensemble.PRIOR_COMPARISON_CELLS = original["prior"]
        subject.ensemble.SELECTION_VERSION_RANGE = original["selection"]
        subject.ensemble.COMPONENT_COMBINER = original["combiner"]
        subject.ensemble.NATIVE_NULL = original["null"]
        subject.ensemble.MECHANISM = original["mechanism"]
        subject.ensemble.COMPONENT_WEIGHT = original["weight"]
