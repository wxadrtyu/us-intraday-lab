from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import export_v11098_forward_contract as contract


def test_exporter_uses_branch_causal_campaign() -> None:
    assert contract.branch.EARLY_MINIMUM_ENTRY_BAR == 11
    assert contract.branch.LATE_MINIMUM_ENTRY_BAR == 24


def test_frozen_branch_contract_is_self_authenticating() -> None:
    path = Path(__file__).parents[3] / "research/results/2026-09-03-v11098-forward-contract.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = payload.pop("contract_sha256")
    observed = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert observed == expected
    assert payload["candidate_id"] == "lev-v11098-2ddc1d07c9cfe31e"
    assert payload["execution"]["transfer_fill_minimum_entry_bar"] == 11
    assert payload["execution"]["modern_fallback_fill_minimum_entry_bar"] == 24
