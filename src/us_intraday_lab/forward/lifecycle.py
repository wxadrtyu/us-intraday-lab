"""Evidence-linked writes for the paper ranking lifecycle."""

from __future__ import annotations

import json
from datetime import datetime

from us_intraday_lab.contracts.registry import RegistryEvent, RegistryState
from us_intraday_lab.forward.ranking import RankingResult
from us_intraday_lab.registry.store import RegistryStore


def promote_ranked(
    store: RegistryStore,
    result: RankingResult,
    *,
    occurred_at: datetime,
    actor: str = "forward-evaluator",
) -> RegistryEvent:
    """Promote an observing strategy with immutable evidence and score references."""

    return store.transition_strategy(
        result.strategy_id,
        to_state="paper_ranked",
        idempotency_key=f"forward-ranked:{result.evidence_id}",
        actor=actor,
        reason_code="FORWARD_HARD_GATES_AND_RANKING_PASSED",
        immutable_refs={
            "forward_evidence_id": result.evidence_id,
            "rank": str(result.rank),
            "quality_score": format(result.quality_score, ".12g"),
            "component_values": json.dumps(
                dict(result.component_values), sort_keys=True, separators=(",", ":")
            ),
            "component_scores": json.dumps(
                dict(result.component_scores), sort_keys=True, separators=(",", ":")
            ),
            "ranking_weights": json.dumps(
                dict(result.weights), sort_keys=True, separators=(",", ":")
            ),
        },
        occurred_at=occurred_at,
    )


def explicit_transition(
    store: RegistryStore,
    strategy_id: str,
    *,
    to_state: RegistryState,
    evidence_id: str,
    reason_code: str,
    idempotency_key: str,
    occurred_at: datetime,
    actor: str = "forward-evaluator",
) -> RegistryEvent:
    """Pause, review, restore, retire, or promote without deleting prior evidence."""

    return store.transition_strategy(
        strategy_id,
        to_state=to_state,
        idempotency_key=idempotency_key,
        actor=actor,
        reason_code=reason_code,
        immutable_refs={"forward_evidence_id": evidence_id},
        occurred_at=occurred_at,
    )
