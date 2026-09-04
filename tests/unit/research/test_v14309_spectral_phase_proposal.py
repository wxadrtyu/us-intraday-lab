from __future__ import annotations

import json
from pathlib import Path


def test_v14309_spectral_phase_campaign_is_frozen_before_implementation() -> None:
    proposal = json.loads(
        (
            Path(__file__).parents[3]
            / "research/proposals/full_universe_intraday_v14309_v14408_spectral_phase_alpha/proposal.json"
        ).read_text(encoding="utf-8")
    )
    assert proposal["status"] == "FROZEN_BEFORE_OUTCOME_SCAN"
    assert proposal["first_version"] == 14309
    assert proposal["last_version"] == 14408
    assert proposal["planned_versions"] == 100
    assert proposal["planned_parameter_cells"] == 1000
    assert proposal["prior_comparison_cells"] == 337_183
    assert proposal["cumulative_comparison_cells"] == 338_183
    assert proposal["execution"]["gross_limit"] == 1.0
    assert proposal["execution"]["overnight"] is False
