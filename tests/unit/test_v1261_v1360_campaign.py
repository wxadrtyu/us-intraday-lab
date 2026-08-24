from __future__ import annotations

import json
from pathlib import Path


def test_v1261_campaign_preregisters_one_hundred_versions() -> None:
    root = Path(__file__).parents[2]
    proposal = json.loads(
        (
            root
            / "research"
            / "proposals"
            / "full_universe_intraday_v1261_v1360"
            / "proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["version_range"] == [1261, 1360]
    assert proposal["version_count"] == 100
    assert proposal["planned_cells"] == 400
    assert proposal["cumulative_comparison_cells"] == 68_355


def test_v1261_campaign_uses_distinct_component_labels_and_ids() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[2]
            / "research"
            / "proposals"
            / "full_universe_intraday_v1261_v1360"
            / "proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["components"] == {
        "anchor": "lev-v45e-0d302fbf92727a31",
        "reversal": "lev-v580-a8e415fa00879183",
        "continuation": "lev-v60-b528b229cefeace2",
    }
