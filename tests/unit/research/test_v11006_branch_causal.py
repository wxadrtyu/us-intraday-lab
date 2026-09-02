from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v11006_v11105_branch_causal as campaign


def test_branch_clock_and_version_contract() -> None:
    assert (campaign.FIRST_VERSION, campaign.LAST_VERSION) == (11006, 11105)
    assert campaign.LAST_VERSION - campaign.FIRST_VERSION + 1 == 100
    assert campaign.EARLY_MINIMUM_ENTRY_BAR == 11
    assert campaign.LATE_MINIMUM_ENTRY_BAR == 24


def test_parent_builder_freezes_both_timing_paths(monkeypatch) -> None:
    minima = []

    def fake_scenarios(cube, frozen, model, minimum):
        minima.append(minimum)
        return tuple(type("Stream", (), {})() for _ in range(3))

    monkeypatch.setattr(campaign, "_scaled_scenarios", fake_scenarios)
    streams = campaign._branch_parent_streams(object(), {}, object())
    assert len(streams) == 3
    assert minima == [11, 24]
    assert all(id(stream) in campaign._late_by_early for stream in streams)
