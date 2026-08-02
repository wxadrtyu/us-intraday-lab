"""SQLite WAL store for immutable strategy definitions and lifecycle events."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import closing, contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

from us_intraday_lab.contracts.registry import RegistryEvent, RegistryState
from us_intraday_lab.contracts.strategies import StrategyDefinition
from us_intraday_lab.contracts.validation import ValidationDecision
from us_intraday_lab.registry.lifecycle import (
    KNOWN_STATES,
    PROMOTION_STATES,
    LifecycleError,
    require_allowed_transition,
)

BUSY_TIMEOUT_MS = 5_000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REASON_CODE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_MIGRATION = Path(__file__).with_name("migrations") / "001_initial.sql"


class IdempotencyConflict(RuntimeError):
    """Raised when a key is retried with a different immutable request."""


class ImmutableRecordConflict(RuntimeError):
    """Raised when an immutable identifier is reused for different content."""


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utc(value: object, *, name: str) -> datetime:
    if type(value) is not datetime:
        raise TypeError(f"{name} must be an exact datetime")
    if value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be timezone-aware UTC")
    return value.astimezone(UTC)


def _nonempty(value: object, *, name: str, maximum: int = 256) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{name} must be a non-empty exact string")
    if len(value) > maximum:
        raise ValueError(f"{name} must contain at most {maximum} characters")
    return value


def _refs(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise ValueError("immutable_refs must be a non-empty mapping")
    normalized: dict[str, str] = {}
    for key, item in value.items():
        normalized[_nonempty(key, name="immutable_refs key")] = _nonempty(
            item,
            name=f"immutable_refs[{key}]",
        )
    return dict(sorted(normalized.items()))


def _event_request_hash(payload: Mapping[str, object]) -> str:
    return _sha256(_canonical_json(payload))


class RegistryStore:
    """Own all writes to the research registry and enforce atomic transitions."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError("path must be a pathlib.Path")
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=BUSY_TIMEOUT_MS / 1_000,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _initialize(self) -> None:
        migration = _MIGRATION.read_text(encoding="utf-8")
        with closing(self._connect()) as connection:
            connection.executescript(migration)

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.execute("COMMIT")
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()

    def connection_pragmas(self) -> dict[str, int | str]:
        with closing(self._connect()) as connection:
            return {
                "foreign_keys": int(connection.execute("PRAGMA foreign_keys").fetchone()[0]),
                "journal_mode": str(connection.execute("PRAGMA journal_mode").fetchone()[0]),
                "busy_timeout": int(connection.execute("PRAGMA busy_timeout").fetchone()[0]),
            }

    def _existing_idempotent_event(
        self,
        connection: sqlite3.Connection,
        *,
        idempotency_key: str,
        request_hash: str,
    ) -> RegistryEvent | None:
        row = connection.execute(
            """
            SELECT * FROM registry_events
            WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        ).fetchone()
        if row is None:
            return None
        if row["idempotency_payload_sha256"] != request_hash:
            raise IdempotencyConflict("IDEMPOTENCY_KEY_CONTENT_MISMATCH")
        return _row_to_event(row)

    def register_strategy(
        self,
        definition: StrategyDefinition,
        *,
        content_sha256: str,
        idempotency_key: str,
        actor: str,
        occurred_at: datetime,
    ) -> RegistryEvent:
        if type(definition) is not StrategyDefinition:
            raise TypeError("definition must be an exact StrategyDefinition")
        validated = StrategyDefinition.model_validate(definition.model_dump(mode="python"))
        if type(content_sha256) is not str or _SHA256.fullmatch(content_sha256) is None:
            raise ValueError("content_sha256 must be a lowercase SHA-256 digest")
        definition_json = _canonical_json(validated.model_dump(mode="json"))
        if _sha256(definition_json) != content_sha256:
            raise ValueError("content_sha256 must match canonical strategy definition")
        key = _nonempty(idempotency_key, name="idempotency_key")
        retained_actor = _nonempty(actor, name="actor")
        timestamp = _utc(occurred_at, name="occurred_at")
        refs = {"content_sha256": content_sha256}
        request_hash = _event_request_hash(
            {
                "actor": retained_actor,
                "content_sha256": content_sha256,
                "occurred_at": timestamp.isoformat(),
                "operation": "register_strategy",
                "strategy_id": validated.strategy_id,
            }
        )
        event = RegistryEvent(
            event_id=_derived_event_id(key, request_hash),
            strategy_id=validated.strategy_id,
            from_state=None,
            to_state="generated",
            actor=retained_actor,
            reason_code="STRATEGY_GENERATED",
            immutable_refs=refs,
            occurred_at=timestamp,
        )
        with self._transaction() as connection:
            existing_event = self._existing_idempotent_event(
                connection,
                idempotency_key=key,
                request_hash=request_hash,
            )
            if existing_event is not None:
                return existing_event
            conflict = connection.execute(
                """
                SELECT strategy_id, content_sha256 FROM strategy_definitions
                WHERE strategy_id = ? OR content_sha256 = ?
                """,
                (validated.strategy_id, content_sha256),
            ).fetchone()
            if conflict is not None:
                raise ImmutableRecordConflict("IMMUTABLE_STRATEGY_CONFLICT")
            connection.execute(
                """
                INSERT INTO strategy_definitions (
                    content_sha256, strategy_id, definition_json, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (content_sha256, validated.strategy_id, definition_json, timestamp.isoformat()),
            )
            self._insert_event(
                connection,
                event=event,
                idempotency_key=key,
                request_hash=request_hash,
            )
            connection.execute(
                """
                INSERT INTO strategy_current_state (
                    strategy_id, current_state, last_event_id, updated_at
                ) VALUES (?, ?, ?, ?)
                """,
                (validated.strategy_id, "generated", event.event_id, timestamp.isoformat()),
            )
        return event

    def record_validation_decision(
        self,
        decision: ValidationDecision,
    ) -> ValidationDecision:
        if type(decision) is not ValidationDecision:
            raise TypeError("decision must be an exact ValidationDecision")
        validated = ValidationDecision.model_validate(decision.model_dump(mode="python"))
        decision_json = _canonical_json(validated.model_dump(mode="json"))
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT decision_json FROM validation_decisions WHERE decision_id = ?",
                (validated.decision_id,),
            ).fetchone()
            if existing is not None:
                if existing["decision_json"] != decision_json:
                    raise ImmutableRecordConflict("IMMUTABLE_DECISION_CONFLICT")
                return ValidationDecision.model_validate_json(existing["decision_json"])
            connection.execute(
                """
                INSERT INTO validation_decisions (
                    decision_id, strategy_id, split_id, decision, decision_json, decided_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    validated.decision_id,
                    validated.strategy_id,
                    validated.split_id,
                    validated.decision,
                    decision_json,
                    validated.decided_at.isoformat(),
                ),
            )
        return validated

    def transition_strategy(
        self,
        strategy_id: str,
        *,
        to_state: RegistryState,
        idempotency_key: str,
        actor: str,
        reason_code: str,
        immutable_refs: Mapping[str, str],
        occurred_at: datetime,
    ) -> RegistryEvent:
        retained_strategy_id = _nonempty(strategy_id, name="strategy_id")
        if type(to_state) is not str or to_state not in KNOWN_STATES:
            raise ValueError("to_state is not a known registry state")
        key = _nonempty(idempotency_key, name="idempotency_key")
        retained_actor = _nonempty(actor, name="actor")
        if type(reason_code) is not str or _REASON_CODE.fullmatch(reason_code) is None:
            raise ValueError("reason_code must be an uppercase stable code")
        refs = _refs(immutable_refs)
        timestamp = _utc(occurred_at, name="occurred_at")
        request_hash = _event_request_hash(
            {
                "actor": retained_actor,
                "immutable_refs": refs,
                "occurred_at": timestamp.isoformat(),
                "operation": "transition_strategy",
                "reason_code": reason_code,
                "strategy_id": retained_strategy_id,
                "to_state": to_state,
            }
        )
        with self._transaction() as connection:
            existing_event = self._existing_idempotent_event(
                connection,
                idempotency_key=key,
                request_hash=request_hash,
            )
            if existing_event is not None:
                return existing_event
            current = connection.execute(
                "SELECT current_state FROM strategy_current_state WHERE strategy_id = ?",
                (retained_strategy_id,),
            ).fetchone()
            if current is None:
                raise LifecycleError("STRATEGY_NOT_REGISTERED")
            from_state = _stored_state(current["current_state"])
            require_allowed_transition(from_state, to_state)
            if to_state in PROMOTION_STATES:
                self._require_passing_decision(
                    connection,
                    strategy_id=retained_strategy_id,
                    immutable_refs=refs,
                )
            event = RegistryEvent(
                event_id=_derived_event_id(key, request_hash),
                strategy_id=retained_strategy_id,
                from_state=from_state,
                to_state=to_state,
                actor=retained_actor,
                reason_code=reason_code,
                immutable_refs=refs,
                occurred_at=timestamp,
            )
            self._insert_event(
                connection,
                event=event,
                idempotency_key=key,
                request_hash=request_hash,
            )
            updated = connection.execute(
                """
                UPDATE strategy_current_state
                SET current_state = ?, last_event_id = ?, updated_at = ?
                WHERE strategy_id = ? AND current_state = ?
                """,
                (
                    to_state,
                    event.event_id,
                    timestamp.isoformat(),
                    retained_strategy_id,
                    from_state,
                ),
            )
            if updated.rowcount != 1:
                raise LifecycleError("CONCURRENT_STATE_TRANSITION")
        return event

    def _require_passing_decision(
        self,
        connection: sqlite3.Connection,
        *,
        strategy_id: str,
        immutable_refs: Mapping[str, str],
    ) -> None:
        decision_id = immutable_refs.get("decision_id")
        if decision_id is None:
            raise LifecycleError("PASSING_VALIDATION_DECISION_REQUIRED")
        row = connection.execute(
            "SELECT decision_json FROM validation_decisions WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        if row is None:
            raise LifecycleError("PASSING_VALIDATION_DECISION_REQUIRED")
        decision = ValidationDecision.model_validate_json(row["decision_json"])
        if (
            decision.strategy_id != strategy_id
            or decision.decision != "PROMOTE_TO_PAPER_SHADOW"
            or not all(gate.passed for gate in decision.gate_results)
        ):
            raise LifecycleError("PASSING_VALIDATION_DECISION_REQUIRED")

    def _insert_event(
        self,
        connection: sqlite3.Connection,
        *,
        event: RegistryEvent,
        idempotency_key: str,
        request_hash: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO registry_events (
                event_id, idempotency_key, idempotency_payload_sha256,
                strategy_id, from_state, to_state, actor, reason_code,
                immutable_refs_json, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                idempotency_key,
                request_hash,
                event.strategy_id,
                event.from_state,
                event.to_state,
                event.actor,
                event.reason_code,
                _canonical_json(dict(event.immutable_refs)),
                event.occurred_at.isoformat(),
            ),
        )

    def get_current_state(self, strategy_id: str) -> RegistryState | None:
        retained = _nonempty(strategy_id, name="strategy_id")
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT current_state FROM strategy_current_state WHERE strategy_id = ?",
                (retained,),
            ).fetchone()
        return None if row is None else _stored_state(row["current_state"])

    def get_strategy_definition(self, strategy_id: str) -> StrategyDefinition | None:
        retained = _nonempty(strategy_id, name="strategy_id")
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT definition_json FROM strategy_definitions WHERE strategy_id = ?",
                (retained,),
            ).fetchone()
        return (
            None if row is None else StrategyDefinition.model_validate_json(row["definition_json"])
        )

    def get_validation_decision(self, decision_id: str) -> ValidationDecision | None:
        retained = _nonempty(decision_id, name="decision_id")
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT decision_json FROM validation_decisions WHERE decision_id = ?",
                (retained,),
            ).fetchone()
        return None if row is None else ValidationDecision.model_validate_json(row["decision_json"])

    def list_events(self, strategy_id: str) -> tuple[RegistryEvent, ...]:
        retained = _nonempty(strategy_id, name="strategy_id")
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM registry_events
                WHERE strategy_id = ?
                ORDER BY sequence_no
                """,
                (retained,),
            ).fetchall()
        return tuple(_row_to_event(row) for row in rows)


def _derived_event_id(idempotency_key: str, request_hash: str) -> str:
    return "event-" + _sha256(f"{idempotency_key}\0{request_hash}")


def _stored_state(value: object) -> RegistryState:
    if type(value) is not str or value not in KNOWN_STATES:
        raise ValueError("stored current_state is not a known registry state")
    return value


def _row_to_event(row: sqlite3.Row) -> RegistryEvent:
    refs = json.loads(row["immutable_refs_json"])
    if not isinstance(refs, dict):
        raise TypeError("stored immutable_refs_json must decode to an object")
    return RegistryEvent(
        event_id=row["event_id"],
        strategy_id=row["strategy_id"],
        from_state=row["from_state"],
        to_state=row["to_state"],
        actor=row["actor"],
        reason_code=row["reason_code"],
        immutable_refs=cast("dict[str, str]", refs),
        occurred_at=datetime.fromisoformat(row["occurred_at"]),
    )
