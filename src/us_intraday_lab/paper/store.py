"""SQLite WAL ledger for restart-safe paper execution evidence."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from us_intraday_lab.contracts.market import MarketBarClosed
from us_intraday_lab.contracts.orders import OrderIntent
from us_intraday_lab.contracts.paper import (
    BrokerOrder,
    PaperCheckpoint,
    PaperSession,
    PositionSnapshot,
    RiskDecision,
)

BUSY_TIMEOUT_MS = 5_000
_MIGRATION = Path(__file__).with_name("migrations") / "001_initial.sql"
_TABLES = (
    "incident_events",
    "market_events",
    "order_events",
    "order_intents",
    "paper_checkpoints",
    "paper_sessions",
    "position_snapshots",
    "reconciliation_runs",
    "risk_decisions",
    "strategy_session_state",
)


class PaperIdempotencyConflict(RuntimeError):
    """A reused external idempotency key carries different immutable content."""


class PaperImmutableConflict(RuntimeError):
    """An immutable paper-ledger identifier was reused with different content."""


class PaperStoreCircuitOpen(RuntimeError):
    """Writes are disabled after a database failure until process recovery."""


@dataclass(frozen=True, slots=True)
class StoredOrderBundle:
    intent: OrderIntent
    risk_decision: RiskDecision
    broker_order: BrokerOrder
    checkpoint: PaperCheckpoint
    order_event_id: str


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _model_json(model: BaseModel) -> str:
    return _canonical_json(model.model_dump(mode="json"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PaperStore:
    """Own paper-session writes and fail closed after any SQLite write error."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError("path must be a pathlib.Path")
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._entry_writes_disabled = False
        self._initialize()

    @property
    def entry_writes_disabled(self) -> bool:
        return self._entry_writes_disabled

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
        with closing(self._connect()) as connection:
            connection.executescript(_MIGRATION.read_text(encoding="utf-8"))

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        if self._entry_writes_disabled:
            raise PaperStoreCircuitOpen("PAPER_STORE_WRITE_CIRCUIT_OPEN")
        try:
            connection = self._connect()
        except sqlite3.Error:
            self._entry_writes_disabled = True
            raise
        try:
            connection.execute("BEGIN IMMEDIATE")
            if self._entry_writes_disabled:
                raise PaperStoreCircuitOpen("PAPER_STORE_WRITE_CIRCUIT_OPEN")
            yield connection
            connection.execute("COMMIT")
        except BaseException as error:
            if isinstance(error, sqlite3.Error):
                self._entry_writes_disabled = True
            if connection.in_transaction:
                try:
                    connection.execute("ROLLBACK")
                except sqlite3.Error:
                    self._entry_writes_disabled = True
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

    def table_names(self) -> tuple[str, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        return tuple(row["name"] for row in rows)

    def row_counts(self) -> dict[str, int]:
        with closing(self._connect()) as connection:
            return {
                table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
                for table in _TABLES
            }

    def create_session(self, session: PaperSession) -> PaperSession:
        if type(session) is not PaperSession:
            raise TypeError("session must be an exact PaperSession")
        retained = PaperSession.model_validate(session.model_dump(mode="python"))
        content = _model_json(retained)
        digest = _sha256(content)
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT session_json, content_sha256 FROM paper_sessions WHERE paper_session_id = ?",
                (retained.paper_session_id,),
            ).fetchone()
            if row is not None:
                if row["content_sha256"] != digest or row["session_json"] != content:
                    raise PaperImmutableConflict("IMMUTABLE_SESSION_CONFLICT")
                return PaperSession.model_validate_json(row["session_json"])
            connection.execute(
                """
                INSERT INTO paper_sessions (
                    paper_session_id, session_date, status, session_json,
                    content_sha256, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    retained.paper_session_id,
                    retained.session_date.isoformat(),
                    retained.status,
                    content,
                    digest,
                    retained.created_at.isoformat(),
                ),
            )
        return retained

    def append_market_event(
        self,
        paper_session_id: str,
        event: MarketBarClosed,
    ) -> MarketBarClosed:
        if type(event) is not MarketBarClosed:
            raise TypeError("event must be an exact MarketBarClosed")
        retained = MarketBarClosed.model_validate(event.model_dump(mode="python"))
        content = _model_json(retained)
        digest = _sha256(content)
        with self._transaction() as connection:
            self._require_session(connection, paper_session_id)
            row = connection.execute(
                """
                SELECT paper_session_id, event_json, content_sha256
                FROM market_events WHERE provider_event_id = ?
                """,
                (retained.provider_event_id,),
            ).fetchone()
            if row is not None:
                if (
                    row["paper_session_id"] != paper_session_id
                    or row["content_sha256"] != digest
                    or row["event_json"] != content
                ):
                    raise PaperIdempotencyConflict("PROVIDER_EVENT_CONTENT_MISMATCH")
                return MarketBarClosed.model_validate_json(row["event_json"])
            connection.execute(
                """
                INSERT INTO market_events (
                    provider_event_id, paper_session_id, symbol, available_at,
                    event_json, content_sha256
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    retained.provider_event_id,
                    paper_session_id,
                    retained.symbol,
                    retained.available_at.isoformat(),
                    content,
                    digest,
                ),
            )
        return retained

    def record_order_bundle(
        self,
        *,
        intent: OrderIntent,
        risk_decision: RiskDecision,
        broker_order: BrokerOrder,
        checkpoint: PaperCheckpoint,
    ) -> StoredOrderBundle:
        if type(intent) is not OrderIntent:
            raise TypeError("intent must be an exact OrderIntent")
        if type(risk_decision) is not RiskDecision:
            raise TypeError("risk_decision must be an exact RiskDecision")
        if type(broker_order) is not BrokerOrder:
            raise TypeError("broker_order must be an exact BrokerOrder")
        if type(checkpoint) is not PaperCheckpoint:
            raise TypeError("checkpoint must be an exact PaperCheckpoint")
        retained_intent = OrderIntent.model_validate(intent.model_dump(mode="python"))
        retained_risk = RiskDecision.model_validate(risk_decision.model_dump(mode="python"))
        retained_order = BrokerOrder.model_validate(broker_order.model_dump(mode="python"))
        retained_checkpoint = PaperCheckpoint.model_validate(checkpoint.model_dump(mode="python"))
        self._validate_bundle(
            intent=retained_intent,
            risk_decision=retained_risk,
            broker_order=retained_order,
            checkpoint=retained_checkpoint,
        )
        intent_json = _model_json(retained_intent)
        risk_json = _model_json(retained_risk)
        order_json = _model_json(retained_order)
        checkpoint_json = _model_json(retained_checkpoint)
        intent_hash = _sha256(intent_json)
        risk_hash = _sha256(risk_json)
        order_hash = _sha256(order_json)
        checkpoint_hash = _sha256(checkpoint_json)
        order_event_id = "paper-order-event-" + order_hash
        with self._transaction() as connection:
            session = self._require_session(connection, retained_intent.run_id)
            if retained_intent.session != session.session_date:
                raise ValueError("intent session must match the paper session")
            self._insert_or_verify_intent(
                connection,
                retained_intent,
                content=intent_json,
                digest=intent_hash,
            )
            self._insert_or_verify_risk(
                connection,
                retained_intent.run_id,
                retained_risk,
                content=risk_json,
                digest=risk_hash,
            )
            self._insert_or_verify_order_event(
                connection,
                retained_intent.run_id,
                retained_order,
                order_event_id=order_event_id,
                content=order_json,
                digest=order_hash,
            )
            self._insert_or_verify_checkpoint(
                connection,
                retained_checkpoint,
                content=checkpoint_json,
                digest=checkpoint_hash,
            )
        return StoredOrderBundle(
            intent=retained_intent,
            risk_decision=retained_risk,
            broker_order=retained_order,
            checkpoint=retained_checkpoint,
            order_event_id=order_event_id,
        )

    @staticmethod
    def _validate_bundle(
        *,
        intent: OrderIntent,
        risk_decision: RiskDecision,
        broker_order: BrokerOrder,
        checkpoint: PaperCheckpoint,
    ) -> None:
        if risk_decision.idempotency_key != intent.idempotency_key:
            raise ValueError("risk decision must reference the order intent")
        if not risk_decision.approved:
            raise ValueError("a submitted broker order requires approved risk")
        if broker_order.client_order_id != intent.idempotency_key:
            raise ValueError("broker order must reference the order intent")
        if checkpoint.paper_session_id != intent.run_id:
            raise ValueError("checkpoint must reference the paper session")
        if broker_order.submitted_at < intent.eligible_time:
            raise ValueError("broker submission must not precede intent eligibility")
        if risk_decision.decided_at > broker_order.submitted_at:
            raise ValueError("risk decision must not follow broker submission")
        if checkpoint.created_at < broker_order.updated_at:
            raise ValueError("checkpoint must not precede broker order evidence")
        if (
            broker_order.symbol != intent.symbol
            or broker_order.side != intent.side
            or broker_order.order_type != intent.order_type
            or broker_order.quantity != intent.quantity
        ):
            raise ValueError("broker order must match immutable intent fields")

    @staticmethod
    def _require_session(connection: sqlite3.Connection, paper_session_id: str) -> PaperSession:
        if type(paper_session_id) is not str or not paper_session_id:
            raise ValueError("paper_session_id must be a non-empty exact string")
        row = connection.execute(
            "SELECT session_json FROM paper_sessions WHERE paper_session_id = ?",
            (paper_session_id,),
        ).fetchone()
        if row is None:
            raise ValueError("PAPER_SESSION_NOT_FOUND")
        return PaperSession.model_validate_json(row["session_json"])

    @staticmethod
    def _insert_or_verify_intent(
        connection: sqlite3.Connection,
        intent: OrderIntent,
        *,
        content: str,
        digest: str,
    ) -> None:
        row = connection.execute(
            "SELECT intent_json, content_sha256 FROM order_intents WHERE idempotency_key = ?",
            (intent.idempotency_key,),
        ).fetchone()
        if row is not None:
            if row["content_sha256"] != digest or row["intent_json"] != content:
                raise PaperIdempotencyConflict("IDEMPOTENCY_KEY_CONTENT_MISMATCH")
            return
        connection.execute(
            """
            INSERT INTO order_intents (
                idempotency_key, paper_session_id, strategy_id, symbol,
                intent_json, content_sha256, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                intent.idempotency_key,
                intent.run_id,
                intent.strategy_id,
                intent.symbol,
                content,
                digest,
                intent.eligible_time.isoformat(),
            ),
        )

    @staticmethod
    def _insert_or_verify_risk(
        connection: sqlite3.Connection,
        paper_session_id: str,
        decision: RiskDecision,
        *,
        content: str,
        digest: str,
    ) -> None:
        row = connection.execute(
            "SELECT decision_json, content_sha256 FROM risk_decisions WHERE idempotency_key = ?",
            (decision.idempotency_key,),
        ).fetchone()
        if row is not None:
            if row["content_sha256"] != digest or row["decision_json"] != content:
                raise PaperIdempotencyConflict("RISK_DECISION_CONTENT_MISMATCH")
            return
        connection.execute(
            """
            INSERT INTO risk_decisions (
                decision_id, idempotency_key, paper_session_id, approved,
                reason_code, decision_json, content_sha256, decided_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision.decision_id,
                decision.idempotency_key,
                paper_session_id,
                int(decision.approved),
                decision.reason_code,
                content,
                digest,
                decision.decided_at.isoformat(),
            ),
        )

    @staticmethod
    def _insert_or_verify_order_event(
        connection: sqlite3.Connection,
        paper_session_id: str,
        order: BrokerOrder,
        *,
        order_event_id: str,
        content: str,
        digest: str,
    ) -> None:
        row = connection.execute(
            "SELECT event_json, content_sha256 FROM order_events WHERE order_event_id = ?",
            (order_event_id,),
        ).fetchone()
        if row is not None:
            if row["content_sha256"] != digest or row["event_json"] != content:
                raise PaperImmutableConflict("IMMUTABLE_ORDER_EVENT_CONFLICT")
            return
        connection.execute(
            """
            INSERT INTO order_events (
                order_event_id, paper_session_id, broker_order_id, idempotency_key,
                status, event_json, content_sha256, occurred_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order_event_id,
                paper_session_id,
                order.broker_order_id,
                order.client_order_id,
                order.status,
                content,
                digest,
                order.updated_at.isoformat(),
            ),
        )

    @staticmethod
    def _insert_or_verify_checkpoint(
        connection: sqlite3.Connection,
        checkpoint: PaperCheckpoint,
        *,
        content: str,
        digest: str,
    ) -> None:
        row = connection.execute(
            """
            SELECT checkpoint_json, content_sha256 FROM paper_checkpoints
            WHERE checkpoint_id = ? OR (
                paper_session_id = ? AND event_sequence = ?
            )
            """,
            (
                checkpoint.checkpoint_id,
                checkpoint.paper_session_id,
                checkpoint.event_sequence,
            ),
        ).fetchone()
        if row is not None:
            if row["content_sha256"] != digest or row["checkpoint_json"] != content:
                raise PaperImmutableConflict("IMMUTABLE_CHECKPOINT_CONFLICT")
            return
        previous = connection.execute(
            """
            SELECT MAX(event_sequence) FROM paper_checkpoints
            WHERE paper_session_id = ?
            """,
            (checkpoint.paper_session_id,),
        ).fetchone()[0]
        expected_sequence = 1 if previous is None else int(previous) + 1
        if checkpoint.event_sequence != expected_sequence:
            raise PaperImmutableConflict("CHECKPOINT_SEQUENCE_GAP")
        connection.execute(
            """
            INSERT INTO paper_checkpoints (
                checkpoint_id, paper_session_id, event_sequence,
                checkpoint_json, content_sha256, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                checkpoint.checkpoint_id,
                checkpoint.paper_session_id,
                checkpoint.event_sequence,
                content,
                digest,
                checkpoint.created_at.isoformat(),
            ),
        )

    def append_position_snapshot(self, snapshot: PositionSnapshot) -> PositionSnapshot:
        if type(snapshot) is not PositionSnapshot:
            raise TypeError("snapshot must be an exact PositionSnapshot")
        retained = PositionSnapshot.model_validate(snapshot.model_dump(mode="python"))
        content = _model_json(retained)
        digest = _sha256(content)
        with self._transaction() as connection:
            self._require_session(connection, retained.paper_session_id)
            row = connection.execute(
                """
                SELECT snapshot_json, content_sha256 FROM position_snapshots
                WHERE snapshot_id = ?
                """,
                (retained.snapshot_id,),
            ).fetchone()
            if row is not None:
                if row["content_sha256"] != digest or row["snapshot_json"] != content:
                    raise PaperImmutableConflict("IMMUTABLE_SNAPSHOT_CONFLICT")
                return PositionSnapshot.model_validate_json(row["snapshot_json"])
            connection.execute(
                """
                INSERT INTO position_snapshots (
                    snapshot_id, paper_session_id, snapshot_json,
                    content_sha256, observed_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    retained.snapshot_id,
                    retained.paper_session_id,
                    content,
                    digest,
                    retained.observed_at.isoformat(),
                ),
            )
        return retained

    @staticmethod
    def _verified_json(row: sqlite3.Row, *, json_column: str) -> str:
        content = str(row[json_column])
        if _sha256(content) != row["content_sha256"]:
            raise PaperImmutableConflict("STORED_CONTENT_HASH_MISMATCH")
        return content

    def get_session(self, paper_session_id: str) -> PaperSession | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT session_json, content_sha256 FROM paper_sessions
                WHERE paper_session_id = ?
                """,
                (paper_session_id,),
            ).fetchone()
        if row is None:
            return None
        return PaperSession.model_validate_json(
            self._verified_json(row, json_column="session_json")
        )

    def get_order_intent(self, idempotency_key: str) -> OrderIntent | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT intent_json, content_sha256 FROM order_intents
                WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            ).fetchone()
        if row is None:
            return None
        return OrderIntent.model_validate_json(self._verified_json(row, json_column="intent_json"))

    def list_market_events(self, paper_session_id: str) -> tuple[MarketBarClosed, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT event_json, content_sha256 FROM market_events
                WHERE paper_session_id = ? ORDER BY sequence_no
                """,
                (paper_session_id,),
            ).fetchall()
        return tuple(
            MarketBarClosed.model_validate_json(self._verified_json(row, json_column="event_json"))
            for row in rows
        )

    def list_order_events(self, paper_session_id: str) -> tuple[BrokerOrder, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT event_json, content_sha256 FROM order_events
                WHERE paper_session_id = ? ORDER BY sequence_no
                """,
                (paper_session_id,),
            ).fetchall()
        return tuple(
            BrokerOrder.model_validate_json(self._verified_json(row, json_column="event_json"))
            for row in rows
        )

    def list_position_snapshots(self, paper_session_id: str) -> tuple[PositionSnapshot, ...]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT snapshot_json, content_sha256 FROM position_snapshots
                WHERE paper_session_id = ? ORDER BY sequence_no
                """,
                (paper_session_id,),
            ).fetchall()
        return tuple(
            PositionSnapshot.model_validate_json(
                self._verified_json(row, json_column="snapshot_json")
            )
            for row in rows
        )

    def latest_checkpoint(self, paper_session_id: str) -> PaperCheckpoint | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT checkpoint_json, content_sha256 FROM paper_checkpoints
                WHERE paper_session_id = ? ORDER BY event_sequence DESC LIMIT 1
                """,
                (paper_session_id,),
            ).fetchone()
        if row is None:
            return None
        return PaperCheckpoint.model_validate_json(
            self._verified_json(row, json_column="checkpoint_json")
        )
