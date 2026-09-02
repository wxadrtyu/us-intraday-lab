from __future__ import annotations

import json
from pathlib import Path

import evaluate_full_universe_intraday_v9605_v9704_causal_repriced_v9292 as subject


SOURCE = Path(
    r"G:\us-intraday-lab\artifacts\accelerated_research\full-universe-intraday-v42-multifactor-vol-target-causal-execution.json"
)


def test_preregistered_version_and_gate_contract() -> None:
    assert subject.FIRST_VERSION == 9605
    assert subject.LAST_VERSION == 9704
    assert subject.MINIMUM_ENTRY_BAR == subject.GATE_DECISION + 1 == 24


def test_every_v9292_routed_parent_is_executable_after_gate() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    source_map = {item["candidate_id"]: item for item in source["records"]}
    ids = subject.parent.sparse_veto.campaign.base.FILL_PARENTS
    anchors = (
        subject.parent.sparse_veto.campaign.base.prior.route.MODERN_PARENT,
        subject.parent.sparse_veto.campaign.base.prior.route.TRANSFER_PARENT,
        subject.parent.sparse_veto.campaign.base.prior.cash.FALLBACK_PARENT,
    )
    for candidate_id in set((*ids, *anchors)):
        decision = source_map[candidate_id]["definition"]["strategy"]["decision"]
        standard = subject.effective_entry_bar(decision, 0)
        delayed = subject.effective_entry_bar(decision, 1)
        assert standard >= 24
        assert delayed == standard + 1


def test_configure_replaces_noncausal_parent_stream_builder() -> None:
    subject._configure()
    builder = subject.parent.sparse_veto.campaign.base.prior.parent._parent_streams
    assert builder is subject._causal_parent_streams
