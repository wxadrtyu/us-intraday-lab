from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3] / "scripts"))

import evaluate_full_universe_intraday_v4070_v4169_state_routed_v42 as subject


def test_campaign_has_one_hundred_versions_and_fifty_thousand_cells() -> None:
    assert len(subject.specifications()) == 100
    assert len(subject.specifications()) * 500 == 50_000
