"""Fail-closed activation of historically qualified, simulation-only strategies."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _atomic_json(path: Path, value: object) -> None:
    encoded = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if path.read_text(encoding="utf-8") != encoded:
            raise ValueError("paper-shadow activation already exists with different content")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(path)


def _validated_selection(proposal: dict[str, Any], selection: dict[str, Any]) -> None:
    if selection.get("proposal_id") != proposal.get("proposal_id"):
        raise ValueError("proposal identity does not match selection")
    proposal_digest = _sha256_bytes(_canonical(proposal).encode())
    if selection.get("proposal_sha256") != proposal_digest:
        raise ValueError("proposal canonical SHA-256 does not match selection")
    recorded_selection_digest = selection.get("selection_sha256")
    without_digest = dict(selection)
    without_digest.pop("selection_sha256", None)
    if recorded_selection_digest != _sha256_bytes(_canonical(without_digest).encode()):
        raise ValueError("selection canonical SHA-256 is invalid")
    gates = selection.get("gate_results")
    if (
        selection.get("all_development_gates_passed") is not True
        or not isinstance(gates, dict)
        or not gates
        or any(value is not True for value in gates.values())
    ):
        raise ValueError("not all historical gates passed")


def activate_paper_shadow(
    *,
    proposal_path: Path,
    selection_path: Path,
    database_path: Path,
    campaign_id: str,
    output_root: Path,
) -> Path:
    """Activate a frozen winner for signal-only simulation without a broker route."""

    proposal_bytes = proposal_path.read_bytes()
    selection_bytes = selection_path.read_bytes()
    proposal = json.loads(proposal_bytes)
    selection = json.loads(selection_bytes)
    _validated_selection(proposal, selection)
    with sqlite3.connect(database_path) as connection:
        row = connection.execute(
            """
            SELECT proposal_sha256, selection_sha256, winner_id,
                   parameters_json, order_route
            FROM research_shadow_campaigns
            WHERE campaign_id = ?
            """,
            (campaign_id,),
        ).fetchone()
    if row is None:
        raise ValueError("research-shadow campaign does not exist")
    proposal_digest, selection_digest, winner_id, parameters_json, order_route = row
    if order_route != "FORBIDDEN":
        raise ValueError("research-shadow order route is not FORBIDDEN")
    proposal_evidence_digest = _sha256_bytes(_canonical(proposal).encode())
    selection_evidence_digest = str(selection["selection_sha256"])
    if proposal_digest != proposal_evidence_digest:
        raise ValueError("campaign proposal evidence SHA-256 mismatch")
    if selection_digest != selection_evidence_digest:
        raise ValueError("campaign selection evidence SHA-256 mismatch")
    if winner_id != selection.get("winner_id"):
        raise ValueError("campaign winner does not match selection")
    if json.loads(parameters_json) != selection.get("winner_parameters"):
        raise ValueError("campaign parameters do not match selection")
    activation = {
        "schema_version": "1.0.0",
        "strategy_id": winner_id,
        "campaign_id": campaign_id,
        "proposal_id": proposal["proposal_id"],
        "proposal_file_sha256": _sha256_bytes(proposal_bytes),
        "selection_file_sha256": _sha256_bytes(selection_bytes),
        "proposal_evidence_sha256": proposal_evidence_digest,
        "selection_evidence_sha256": selection_evidence_digest,
        "lifecycle_state": "paper_shadow",
        "qualification_basis": "historical_accelerated_hard_gates",
        "historical_gate_results": selection["gate_results"],
        "execution_mode": "signals_and_theoretical_fills_only",
        "order_route": "FORBIDDEN",
        "broker_construction_allowed": False,
        "live_order_submission_allowed": False,
        "prospective_observation": {
            "campaign_continues": True,
            "blocks_paper_shadow": False,
            "blocks_live_orders": True,
        },
    }
    activation["content_sha256"] = _sha256_bytes(_canonical(activation).encode())
    output = (
        output_root.resolve() / "artifacts" / "paper_shadow" / str(winner_id) / "activation.json"
    )
    _atomic_json(output, activation)
    return output
