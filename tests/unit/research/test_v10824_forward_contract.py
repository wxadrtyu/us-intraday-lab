from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import export_v10824_forward_contract as contract


def test_jsonable_preserves_nested_models_without_numpy_values() -> None:
    encoded = contract._jsonable(
        {"array": np.asarray([1.0, 2.0]), "scalar": np.float64(3.0), "tuple": (4, 5)}
    )
    assert encoded == {"array": [1.0, 2.0], "scalar": 3.0, "tuple": [4, 5]}
    json.dumps(encoded)


def test_frozen_contract_is_self_authenticating_and_fail_closed() -> None:
    path = Path(__file__).parents[3] / "research/results/2026-09-03-v10824-forward-contract.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    digest = payload.pop("contract_sha256")
    actual = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert actual == digest
    assert payload["candidate_id"] == contract.CANDIDATE_ID
    assert payload["fit_contract"]["consumed_2026_used_for_fit_or_ranking"] is False
    assert payload["execution"] == {
        "bar_minutes": 5,
        "gross_limit": 1.0,
        "long_only": True,
        "minimum_late_entry_bar": 11,
        "opening_decision_bar": 2,
        "opening_entry_bar": 3,
        "opening_exit_bar": 11,
        "outer_gate_decision_bar": 5,
        "outer_gate_low_exposure": 0.25,
        "overnight": False,
    }
    assert len(payload["parents"]) == 12
