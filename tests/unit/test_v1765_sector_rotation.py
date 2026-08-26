from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[2] / "scripts"))
sector = importlib.import_module("evaluate_full_universe_intraday_v1765_v1864_sector_rotation")


def test_sector_campaign_has_one_hundred_unique_multifactor_hypotheses():
    proposal = json.loads(sector.PROPOSAL.read_text())
    specs = [
        (family, clock, state)
        for family in proposal["families"]
        for clock in proposal["schedules"]
        for state in proposal["state_modes"]
    ]
    assert len(specs) == len({repr(item) for item in specs}) == 100
    assert proposal["version_range"] == [1765, 1864]
    assert all(
        len(factors) >= 3 and len(factors) == len(signs)
        for _, factors, signs in proposal["families"]
    )
    assert proposal["planned_cells"] == 50 * 64 + 50 * 192
    assert proposal["cumulative_comparison_cells"] == 97005 + 12800
    assert {sector.prior.v12.SYMBOLS[i] for i in sector.SECTORS} == set(proposal["universe"])
    assert not {"TQQQ", "SOXL", "SPY"}.intersection(proposal["universe"])


def test_sector_rank_and_relative_values_ignore_risk_asset_levels(monkeypatch):
    monkeypatch.setattr(sector.IntradayPathCube, "factors", lambda self, decision: {})
    cube = object.__new__(sector.SectorCube)
    values = np.arange(16, dtype=float)[None, :]
    cube.prior20 = values.copy()
    cube._features = lambda decision: {"current": values.copy()}
    original = cube.factors(23)
    values[:, :5] = 1e8
    changed = cube.factors(23)
    for name in ("sector_relative", "sector_rank", "sector_prior_rank"):
        np.testing.assert_allclose(original[name], changed[name], equal_nan=True)
        assert np.isnan(changed[name][:, :5]).all()
    np.testing.assert_allclose(original["sector_relative"][:, 5:].mean(), 0)
    assert original["sector_rank"][0, 15] == 1.0


def test_stress_rank_does_not_read_consumed_diagnostics():
    common = {"annualized_return": 0.5, "max_drawdown": 0.1, "information_ratio": 1.1}
    observations = tuple(
        {
            "development_oos_2024_2025": common,
            **{name: common for name in sector.template.DEVELOPMENT_NAMES},
        }
        for _ in range(3)
    )
    before = sector.stress_rank(observations)
    observations[0]["consumed_2026_all"] = {"total_return": 1000}
    observations[1]["consumed_2026q1"] = {"total_return": -1}
    assert sector.stress_rank(observations) == before == (0.5, -0.1, 1.1, 0.5)


def test_correlation_rejects_constant_stream_and_detects_duplication():
    cube = SimpleNamespace(
        masks=lambda: {
            name: np.ones(10, dtype=bool) for name in ("2024", "2025", "development_oos_2024_2025")
        }
    )
    baseline = np.arange(10, dtype=float)
    assert all(
        value is None for value in sector.correlation_report(cube, np.zeros(10), baseline).values()
    )
    assert all(
        np.isclose(value, 1)
        for value in sector.correlation_report(cube, baseline, baseline).values()
    )


def test_rule_execution_selects_sector_and_uses_next_bar_plus_delay(monkeypatch):
    monkeypatch.setattr(sector.prior, "ASSETS", sector.SECTORS.copy())
    monkeypatch.setattr(sector.prior, "_rule_score", lambda *args: np.tile(np.arange(11), (2, 1)))
    opens = np.full((2, 78, 16), 100.0)
    opens[:, 25, 15] = 101.0
    opens[:, 47, 15] = 102.0
    cube = SimpleNamespace(
        sessions=[1, 2],
        rows=np.arange(2),
        opens=opens,
        first=np.broadcast_to(np.arange(78)[None, :, None] * 5, opens.shape),
        boundary_tolerance=0,
    )
    definition = {
        "decision": 23,
        "exit": 47,
        "factors": ("a", "b", "c"),
        "directions": (1, 1, 1),
        "confirmations": 1,
    }
    regular = sector.prior._rule_raw(cube, definition, np.zeros(3), np.ones(3), 0, 0.0009, 0)
    delayed = sector.prior._rule_raw(cube, definition, np.zeros(3), np.ones(3), 0, 0.0009, 1)
    doubled_cost = sector.prior._rule_raw(cube, definition, np.zeros(3), np.ones(3), 0, 0.0018, 0)
    np.testing.assert_allclose(regular.values, 102 / 100 - 1 - 0.0009)
    np.testing.assert_allclose(delayed.values, 102 / 101 - 1 - 0.0009)
    np.testing.assert_allclose(regular.values - doubled_cost.values, 0.0009)
    assert (regular.component_trades == 1).all()
