from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v11608_v11707_v11098_diversified_blend as campaign


def test_v11608_proposal_freezes_one_hundred_bounded_blends() -> None:
    path = (
        Path(__file__).parents[3]
        / "research"
        / "proposals"
        / "full_universe_intraday_v11608_v11707_v11098_diversified_blend"
        / "proposal.json"
    )
    proposal = json.loads(path.read_text(encoding="utf-8"))
    assert proposal["last_version"] - proposal["first_version"] + 1 == 100
    assert proposal["planned_versions"] == 20 * 5
    assert proposal["execution"]["maximum_concurrent_gross"] == 1.0
    assert "development_rank" in proposal["selection_firewall"]


def test_v11608_code_matches_frozen_version_grid() -> None:
    assert campaign.LAST_VERSION - campaign.FIRST_VERSION + 1 == 100
    assert len(campaign.INDEPENDENT_WEIGHTS) == 5
    assert max(campaign.INDEPENDENT_WEIGHTS) <= 0.25
