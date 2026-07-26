"""Isolated strategy runtime state with audited transitions."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum
from types import MappingProxyType
from typing import Literal
from zoneinfo import ZoneInfo

import pandas as pd

from us_intraday_lab.strategy.features import visible_feature_frame

_NEW_YORK = ZoneInfo("America/New_York")
Signal = Literal["ENTER_LONG", "EXIT_LONG", "HOLD"]
AuditOutcome = Literal["accepted", "rejected"]


class RuntimePhase(StrEnum):
    FLAT = "FLAT"
    ENTRY_PENDING = "ENTRY_PENDING"
    LONG = "LONG"
    EXIT_PENDING = "EXIT_PENDING"
    COOLDOWN = "COOLDOWN"
    SESSION_CLOSED = "SESSION_CLOSED"


@dataclass(frozen=True)
class RuntimeKey:
    strategy_id: str
    symbol: str
    session_date: date

    def __post_init__(self) -> None:
        if not self.strategy_id:
            raise ValueError("strategy_id must not be empty")
        if not self.symbol:
            raise ValueError("symbol must not be empty")


@dataclass(frozen=True)
class RuntimeState:
    phase: RuntimePhase = RuntimePhase.FLAT
    entries: int = 0
    opened_at: datetime | None = None
    cooldown_until: datetime | None = None
    last_signal: Signal | None = None
    last_signal_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.entries < 0:
            raise ValueError("runtime state invariant: entries must not be negative")
        for timestamp in (self.opened_at, self.cooldown_until, self.last_signal_at):
            if timestamp is not None and (
                timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0)
            ):
                raise ValueError("runtime state invariant: timestamps must be aware UTC")
        if (self.last_signal is None) != (self.last_signal_at is None):
            raise ValueError(
                "runtime state invariant: last signal and timestamp must be set together"
            )
        if self.phase in (RuntimePhase.LONG, RuntimePhase.EXIT_PENDING):
            if self.entries == 0 or self.opened_at is None or self.cooldown_until is not None:
                raise ValueError(
                    "runtime state invariant: open position requires entry and opening time"
                )
            return
        if self.phase is RuntimePhase.COOLDOWN:
            if self.opened_at is not None or self.cooldown_until is None:
                raise ValueError(
                    "runtime state invariant: cooldown requires only a cooldown deadline"
                )
            return
        if self.opened_at is not None or self.cooldown_until is not None:
            raise ValueError(
                "runtime state invariant: inactive phase cannot retain position timestamps"
            )


@dataclass(frozen=True)
class RuntimeAuditEvent:
    event_type: Literal["state_transition", "signal"]
    key: RuntimeKey
    event_time: datetime
    outcome: AuditOutcome
    from_phase: RuntimePhase
    to_phase: RuntimePhase
    reason: str


class RuntimeTransitionError(RuntimeError):
    """Typed failure raised when the engine requests an illegal transition."""

    def __init__(
        self,
        *,
        key: RuntimeKey,
        from_phase: RuntimePhase,
        to_phase: RuntimePhase,
    ) -> None:
        super().__init__(
            f"illegal state transition for {key.strategy_id}/{key.symbol}/"
            f"{key.session_date}: {from_phase} -> {to_phase}"
        )
        self.code = "ILLEGAL_STATE_TRANSITION"
        self.key = key
        self.from_phase = from_phase
        self.to_phase = to_phase


_PUBLIC_TRANSITIONS = MappingProxyType(
    {
        RuntimePhase.FLAT: frozenset({RuntimePhase.ENTRY_PENDING, RuntimePhase.SESSION_CLOSED}),
        RuntimePhase.ENTRY_PENDING: frozenset({RuntimePhase.FLAT, RuntimePhase.SESSION_CLOSED}),
        RuntimePhase.LONG: frozenset({RuntimePhase.EXIT_PENDING, RuntimePhase.SESSION_CLOSED}),
        RuntimePhase.EXIT_PENDING: frozenset({RuntimePhase.LONG, RuntimePhase.SESSION_CLOSED}),
        RuntimePhase.COOLDOWN: frozenset({RuntimePhase.FLAT, RuntimePhase.SESSION_CLOSED}),
        RuntimePhase.SESSION_CLOSED: frozenset(),
    }
)
_FILL_TRANSITIONS = MappingProxyType(
    {
        RuntimePhase.ENTRY_PENDING: frozenset({RuntimePhase.LONG}),
        RuntimePhase.EXIT_PENDING: frozenset({RuntimePhase.COOLDOWN}),
    }
)


def _utc_event_time(value: datetime, *, key: RuntimeKey) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("event_time must be timezone-aware UTC")
    timestamp = value.astimezone(UTC)
    if timestamp.astimezone(_NEW_YORK).date() != key.session_date:
        raise ValueError("event_time does not match runtime session_date")
    return timestamp


class StrategyRuntime:
    """Own runtime state keyed strictly by strategy, symbol, and session."""

    def __init__(self) -> None:
        self._states: dict[RuntimeKey, RuntimeState] = {}
        self._audit_events: list[RuntimeAuditEvent] = []

    @property
    def audit_events(self) -> tuple[RuntimeAuditEvent, ...]:
        return tuple(self._audit_events)

    def state_for(self, key: RuntimeKey) -> RuntimeState:
        return self._states.get(key, RuntimeState())

    @staticmethod
    def visible_features(
        features: pd.DataFrame,
        *,
        clock_time: object,
    ) -> pd.DataFrame:
        """Expose completed feature rows through the engine-facing runtime seam."""
        return visible_feature_frame(features, clock_time=clock_time)

    def _save(self, key: RuntimeKey, state: RuntimeState) -> None:
        self._states[key] = state

    def _audit_transition(
        self,
        *,
        key: RuntimeKey,
        event_time: datetime,
        outcome: AuditOutcome,
        from_phase: RuntimePhase,
        to_phase: RuntimePhase,
        reason: str,
    ) -> None:
        self._audit_events.append(
            RuntimeAuditEvent(
                event_type="state_transition",
                key=key,
                event_time=event_time,
                outcome=outcome,
                from_phase=from_phase,
                to_phase=to_phase,
                reason=reason,
            )
        )

    def _require_transition(
        self,
        key: RuntimeKey,
        to_phase: RuntimePhase,
        *,
        event_time: datetime,
        reason: str,
        allowed_transitions: MappingProxyType[
            RuntimePhase, frozenset[RuntimePhase]
        ] = _PUBLIC_TRANSITIONS,
    ) -> tuple[RuntimeState, datetime]:
        timestamp = _utc_event_time(event_time, key=key)
        state = self.state_for(key)
        if to_phase not in allowed_transitions.get(state.phase, frozenset()):
            self._audit_transition(
                key=key,
                event_time=timestamp,
                outcome="rejected",
                from_phase=state.phase,
                to_phase=to_phase,
                reason=reason,
            )
            raise RuntimeTransitionError(
                key=key,
                from_phase=state.phase,
                to_phase=to_phase,
            )
        return state, timestamp

    def transition(
        self,
        key: RuntimeKey,
        to_phase: RuntimePhase,
        *,
        event_time: datetime,
        reason: str = "engine_transition",
    ) -> None:
        state, timestamp = self._require_transition(
            key,
            to_phase,
            event_time=event_time,
            reason=reason,
        )
        next_state = replace(state, phase=to_phase)
        if to_phase in (RuntimePhase.FLAT, RuntimePhase.SESSION_CLOSED):
            next_state = replace(next_state, opened_at=None, cooldown_until=None)
        self._save(key, next_state)
        self._audit_transition(
            key=key,
            event_time=timestamp,
            outcome="accepted",
            from_phase=state.phase,
            to_phase=to_phase,
            reason=reason,
        )

    def record_signal(
        self,
        key: RuntimeKey,
        *,
        signal: Signal,
        event_time: datetime,
    ) -> None:
        timestamp = _utc_event_time(event_time, key=key)
        state = self.state_for(key)
        if state.phase is RuntimePhase.SESSION_CLOSED:
            self._audit_events.append(
                RuntimeAuditEvent(
                    event_type="signal",
                    key=key,
                    event_time=timestamp,
                    outcome="rejected",
                    from_phase=state.phase,
                    to_phase=state.phase,
                    reason="session_closed",
                )
            )
            raise RuntimeTransitionError(
                key=key,
                from_phase=state.phase,
                to_phase=state.phase,
            )
        if signal not in ("ENTER_LONG", "EXIT_LONG", "HOLD"):
            raise ValueError(f"unsupported signal: {signal!r}")
        self._save(
            key,
            replace(state, last_signal=signal, last_signal_at=timestamp),
        )
        self._audit_events.append(
            RuntimeAuditEvent(
                event_type="signal",
                key=key,
                event_time=timestamp,
                outcome="accepted",
                from_phase=state.phase,
                to_phase=state.phase,
                reason=signal,
            )
        )

    def record_order_rejected(
        self,
        key: RuntimeKey,
        *,
        event_time: datetime,
    ) -> None:
        state = self.state_for(key)
        target = (
            RuntimePhase.FLAT if state.phase is RuntimePhase.ENTRY_PENDING else RuntimePhase.LONG
        )
        self.transition(
            key,
            target,
            event_time=event_time,
            reason="order_rejected",
        )

    def mark_entry_filled(
        self,
        key: RuntimeKey,
        *,
        event_time: datetime,
    ) -> None:
        state, timestamp = self._require_transition(
            key,
            RuntimePhase.LONG,
            event_time=event_time,
            reason="opening_fill",
            allowed_transitions=_FILL_TRANSITIONS,
        )
        self._save(
            key,
            replace(
                state,
                phase=RuntimePhase.LONG,
                entries=state.entries + 1,
                opened_at=timestamp,
                cooldown_until=None,
            ),
        )
        self._audit_transition(
            key=key,
            event_time=timestamp,
            outcome="accepted",
            from_phase=state.phase,
            to_phase=RuntimePhase.LONG,
            reason="opening_fill",
        )

    def mark_exit_filled(
        self,
        key: RuntimeKey,
        *,
        event_time: datetime,
        cooldown_minutes: int,
    ) -> None:
        state, timestamp = self._require_transition(
            key,
            RuntimePhase.COOLDOWN,
            event_time=event_time,
            reason="exit_fill",
            allowed_transitions=_FILL_TRANSITIONS,
        )
        if cooldown_minutes <= 0:
            raise ValueError("cooldown_minutes must be positive")
        self._save(
            key,
            replace(
                state,
                phase=RuntimePhase.COOLDOWN,
                opened_at=None,
                cooldown_until=timestamp + timedelta(minutes=cooldown_minutes),
            ),
        )
        self._audit_transition(
            key=key,
            event_time=timestamp,
            outcome="accepted",
            from_phase=state.phase,
            to_phase=RuntimePhase.COOLDOWN,
            reason="exit_fill",
        )

    def holding_minutes(
        self,
        key: RuntimeKey,
        *,
        clock_time: datetime,
    ) -> int | None:
        timestamp = _utc_event_time(clock_time, key=key)
        state = self.state_for(key)
        if state.phase not in (RuntimePhase.LONG, RuntimePhase.EXIT_PENDING):
            return None
        if state.opened_at is None:
            return None
        if timestamp < state.opened_at:
            raise ValueError("clock_time must not precede opening fill")
        return int((timestamp - state.opened_at).total_seconds() // 60)

    def cooldown_active(
        self,
        key: RuntimeKey,
        *,
        clock_time: datetime,
    ) -> bool:
        timestamp = _utc_event_time(clock_time, key=key)
        state = self.state_for(key)
        return (
            state.phase is RuntimePhase.COOLDOWN
            and state.cooldown_until is not None
            and timestamp < state.cooldown_until
        )

    def complete_cooldown(
        self,
        key: RuntimeKey,
        *,
        event_time: datetime,
    ) -> None:
        timestamp = _utc_event_time(event_time, key=key)
        state = self.state_for(key)
        if state.phase is RuntimePhase.SESSION_CLOSED:
            self._audit_transition(
                key=key,
                event_time=timestamp,
                outcome="rejected",
                from_phase=state.phase,
                to_phase=RuntimePhase.FLAT,
                reason="cooldown_elapsed",
            )
            raise RuntimeTransitionError(
                key=key,
                from_phase=state.phase,
                to_phase=RuntimePhase.FLAT,
            )
        if state.cooldown_until is None or timestamp < state.cooldown_until:
            raise ValueError("cooldown has not elapsed")
        self.transition(
            key,
            RuntimePhase.FLAT,
            event_time=timestamp,
            reason="cooldown_elapsed",
        )

    def close_session(self, key: RuntimeKey, *, event_time: datetime) -> None:
        self.transition(
            key,
            RuntimePhase.SESSION_CLOSED,
            event_time=event_time,
            reason="session_closed",
        )
