from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v4170_v4269_dual_parent_routing as subject


def test_campaign_has_one_hundred_versions_and_one_thousand_cells() -> None:
    assert len(subject.specifications()) == 100
    assert len(subject.specifications()) * len(subject.TRANSFER_PARENTS) == 1_000
