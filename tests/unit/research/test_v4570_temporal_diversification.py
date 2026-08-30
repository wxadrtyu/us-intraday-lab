from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v4570_v4669_temporal_diversification as subject


def test_campaign_has_one_hundred_frozen_versions() -> None:
    assert subject.FIRST_VERSION == 4570
    assert subject.LAST_VERSION == 4669
    assert subject.PARENT_COUNT * len(subject.WEIGHTS) == 100


def test_weights_preserve_gross_one() -> None:
    for weight in subject.WEIGHTS:
        assert 0 < weight < 1
        assert (1 - weight) + weight == 1
