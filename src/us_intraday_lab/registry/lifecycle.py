"""Closed lifecycle rules for the historical research registry."""

from __future__ import annotations

from us_intraday_lab.contracts.registry import RegistryState

KNOWN_STATES: frozenset[RegistryState] = frozenset(
    {
        "generated",
        "backtested",
        "validated",
        "candidate",
        "paper_shadow",
        "paper_observing",
        "paper_ranked",
        "leader",
        "review",
        "rejected",
        "paused",
        "retired",
    }
)
ALLOWED_TRANSITIONS: dict[RegistryState, frozenset[RegistryState]] = {
    "generated": frozenset({"candidate", "review"}),
    "candidate": frozenset({"rejected", "paper_shadow", "review"}),
    "paper_shadow": frozenset({"paper_observing", "rejected", "review"}),
    "paper_observing": frozenset({"paper_ranked", "paused", "review"}),
    "paper_ranked": frozenset({"leader", "paused", "review"}),
    "leader": frozenset({"paused", "review"}),
    "review": frozenset({"paused", "retired", "paper_observing"}),
    "rejected": frozenset({"review"}),
    "backtested": frozenset({"review"}),
    "validated": frozenset({"review"}),
    "paused": frozenset({"paper_observing", "review"}),
    "retired": frozenset(),
}
VALIDATION_PROMOTION_STATES = frozenset({"paper_shadow"})
STATE_CAPACITY: dict[RegistryState, int] = {
    "paper_observing": 20,
    "paper_ranked": 5,
    "leader": 3,
}


class LifecycleError(RuntimeError):
    """Raised before an illegal registry transition can mutate the ledger."""


def require_allowed_transition(from_state: RegistryState, to_state: RegistryState) -> None:
    if to_state not in ALLOWED_TRANSITIONS[from_state]:
        raise LifecycleError(f"ILLEGAL_REGISTRY_TRANSITION: {from_state} -> {to_state}")
