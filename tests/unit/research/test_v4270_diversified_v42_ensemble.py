from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v4270_v4369_diversified_v42_ensemble as subject


def test_campaign_has_one_hundred_versions() -> None:
    assert len(subject.specifications()) == 100
