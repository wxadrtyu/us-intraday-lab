from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from us_intraday_lab.paper_shadow_activation import activate_paper_shadow


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _write_inputs(tmp_path: Path, *, order_route: str = "FORBIDDEN") -> tuple[Path, Path, Path]:
    proposal = {
        "proposal_id": "v4",
        "direction": "long_only",
        "lifecycle_state": "research_candidate_awaiting_new_forward_interval",
    }
    proposal_path = tmp_path / "proposal.json"
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
    selection = {
        "proposal_id": "v4",
        "proposal_sha256": hashlib.sha256(_canonical(proposal).encode()).hexdigest(),
        "winner_id": "winner-v4",
        "winner_parameters": {"floor": 0.003},
        "all_development_gates_passed": True,
        "gate_results": {"core": True, "null_test": True},
    }
    selection["selection_sha256"] = hashlib.sha256(_canonical(selection).encode()).hexdigest()
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(json.dumps(selection), encoding="utf-8")
    database = tmp_path / "shadow.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE research_shadow_campaigns (
          campaign_id TEXT PRIMARY KEY,
          proposal_sha256 TEXT NOT NULL,
          selection_sha256 TEXT NOT NULL,
          winner_id TEXT NOT NULL,
          parameters_json TEXT NOT NULL,
          order_route TEXT NOT NULL
        )
        """
    )
    connection.execute(
        "INSERT INTO research_shadow_campaigns VALUES (?, ?, ?, ?, ?, ?)",
        (
            "campaign-v4",
            hashlib.sha256(_canonical(proposal).encode()).hexdigest(),
            str(selection["selection_sha256"]),
            "winner-v4",
            _canonical({"floor": 0.003}),
            order_route,
        ),
    )
    connection.commit()
    connection.close()
    return proposal_path, selection_path, database


def test_activate_historically_qualified_strategy_as_simulation_only(tmp_path: Path) -> None:
    proposal, selection, database = _write_inputs(tmp_path)
    output = activate_paper_shadow(
        proposal_path=proposal,
        selection_path=selection,
        database_path=database,
        campaign_id="campaign-v4",
        output_root=tmp_path,
    )
    activation = json.loads(output.read_text(encoding="utf-8"))
    assert activation["lifecycle_state"] == "paper_shadow"
    assert activation["execution_mode"] == "signals_and_theoretical_fills_only"
    assert activation["order_route"] == "FORBIDDEN"
    assert activation["broker_construction_allowed"] is False
    assert activation["live_order_submission_allowed"] is False
    assert activation["proposal_file_sha256"] == hashlib.sha256(proposal.read_bytes()).hexdigest()
    assert activation["selection_file_sha256"] == hashlib.sha256(selection.read_bytes()).hexdigest()
    assert activation["prospective_observation"]["blocks_paper_shadow"] is False
    assert activation["prospective_observation"]["blocks_live_orders"] is True
    assert output == tmp_path / "artifacts" / "paper_shadow" / "winner-v4" / "activation.json"


def test_activation_fails_closed_when_database_route_is_not_forbidden(tmp_path: Path) -> None:
    proposal, selection, database = _write_inputs(tmp_path, order_route="PAPER")
    with pytest.raises(ValueError, match="order route"):
        activate_paper_shadow(
            proposal_path=proposal,
            selection_path=selection,
            database_path=database,
            campaign_id="campaign-v4",
            output_root=tmp_path,
        )


def test_activation_fails_when_any_historical_gate_failed(tmp_path: Path) -> None:
    proposal, selection, database = _write_inputs(tmp_path)
    payload = json.loads(selection.read_text(encoding="utf-8"))
    payload["gate_results"]["null_test"] = False
    payload.pop("selection_sha256")
    payload["selection_sha256"] = hashlib.sha256(_canonical(payload).encode()).hexdigest()
    selection.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="historical gates"):
        activate_paper_shadow(
            proposal_path=proposal,
            selection_path=selection,
            database_path=database,
            campaign_id="campaign-v4",
            output_root=tmp_path,
        )
