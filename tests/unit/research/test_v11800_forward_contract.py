from __future__ import annotations

import hashlib
import json
from pathlib import Path


def test_v11800_frozen_contract_is_self_authenticating_and_hard_cash() -> None:
    path = Path(__file__).parents[3] / "research/results/2026-09-03-v11800-forward-contract.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = payload.pop("contract_sha256")
    observed = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert observed == expected
    assert payload["candidate_id"] == "lev-v11800-90804cea426c9753"
    assert payload["execution"]["outer_gate_low_exposure"] == 0.0
    assert payload["execution"]["transfer_fill_minimum_entry_bar"] == 11
    assert payload["execution"]["modern_fallback_fill_minimum_entry_bar"] == 24
