from __future__ import annotations

import json
from pathlib import Path

import audit_v9292_forward_causality as subject


SOURCE = Path(r"G:\us-intraday-lab\artifacts\accelerated_research\full-universe-intraday-v42-multifactor-vol-target-causal-execution.json")


def test_v9292_late_route_fails_native_entry_timing_parity() -> None:
    result = subject.audit(json.loads(SOURCE.read_text(encoding="utf-8")))
    assert result["status"] == "REJECTED_NONCAUSAL_LATE_ROUTE_REPRICING_PARITY"
    assert result["paper_activation_allowed"] is False
    assert result["offending_parent_count"] > 0
    assert all(item["native_entry_bar"] < subject.DECLARED_LATE_ENTRY for item in result["offending_parents"])


def test_v9292_route_contains_every_frozen_anchor_and_fill_parent() -> None:
    ids = subject.routed_parent_ids()
    assert len(ids) == len(set(ids))
    assert len(ids) >= 10
