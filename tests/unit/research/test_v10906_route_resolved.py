from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import evaluate_full_universe_intraday_v10906_v11005_route_resolved as campaign


def test_version_and_route_clock_are_preregistered() -> None:
    assert (campaign.FIRST_VERSION, campaign.LAST_VERSION) == (10906, 11005)
    assert campaign.LAST_VERSION - campaign.FIRST_VERSION + 1 == 100
    assert campaign.MINIMUM_ENTRY_BAR == campaign.ROUTE_DECISION_BAR + 1 == 24


def test_all_parent_scenarios_use_route_resolved_minimum(monkeypatch) -> None:
    calls = []

    def fake_sleeve(cube, model, cost, delay, minimum):
        calls.append((cost, delay, minimum))
        return type("Stream", (), {"values": [0.0]})()

    monkeypatch.setattr(campaign.repriced, "_repriced_sleeve", fake_sleeve)
    monkeypatch.setattr(campaign.repriced.v42, "_exposure", lambda *args: [1.0])
    monkeypatch.setattr(campaign.repriced.v42, "_scaled", lambda stream, exposure: stream)
    frozen = {
        "definition": {"lookback": 20, "target_volatility": 0.3, "minimum_exposure": 0.0}
    }
    streams = campaign._route_resolved_parent_streams(object(), frozen, object())
    assert len(streams) == 3
    assert [item[1:] for item in calls] == [(0, 24), (0, 24), (1, 24)]
