from __future__ import annotations

import json
from pathlib import Path


def test_v14109_sign_topology_campaign_is_frozen_before_implementation() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v14109_v14208_sign_topology_alpha/proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == 14109
    assert proposal["last_version"] == 14208
    assert proposal["planned_versions"] == 100
    assert proposal["planned_parameter_cells"] == 1000
    assert proposal["prior_comparison_cells"] == 335_183
    assert proposal["cumulative_comparison_cells"] == 336_183
    assert proposal["diagnostics_not_selection"] == [
        "historical_2018_2020",
        "consumed_2026q1",
        "consumed_2026_all",
    ]
    assert proposal["execution"] == {
        "long_only": True,
        "gross_limit": 1.0,
        "overnight": False,
    }
