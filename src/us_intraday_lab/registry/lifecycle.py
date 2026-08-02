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
        "rejected",
        "paused",
        "retired",
    }
)
ALLOWED_TRANSITIONS: dict[RegistryState, frozenset[RegistryState]] = {
    "generated": frozenset({"candidate"}),
    "candidate": frozenset({"rejected", "paper_shadow"}),
    "paper_shadow": frozenset({"rejected"}),
    "rejected": frozenset(),
    "backtested": frozenset(),
    "validated": frozenset(),
    "paused": frozenset(),
    "retired": frozenset(),
}
PROMOTION_STATES = frozenset({"candidate", "paper_shadow"})


class LifecycleError(RuntimeError):
    """Raised before an illegal registry transition can mutate the ledger."""


def require_allowed_transition(from_state: RegistryState, to_state: RegistryState) -> None:
    if to_state not in ALLOWED_TRANSITIONS[from_state]:
        raise LifecycleError(f"ILLEGAL_REGISTRY_TRANSITION: {from_state} -> {to_state}")
