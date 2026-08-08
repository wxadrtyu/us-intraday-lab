from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


class FinalTestIsolationError(RuntimeError):
    """Raised when a campaign attempts to reuse or replace sealed final evidence."""


@dataclass(frozen=True, slots=True)
class FinalConsumption:
    reservation_token: str
    proposal_id: str
    evidence_sha256: str
    consumed_at: str


def _nonempty(value: str, *, name: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _sha256(value: str, *, name: str) -> str:
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _survivors(values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple or not 1 <= len(values) <= 200:
        raise ValueError("survivor_ids must contain between 1 and 200 strategy IDs")
    if any(type(value) is not str or not value for value in values):
        raise ValueError("survivor_ids must contain non-empty strings")
    if tuple(sorted(values)) != values or len(set(values)) != len(values):
        raise ValueError("survivor_ids must be sorted and unique")
    return values


class CampaignFinalLedger:
    """Transactional campaign-wide one-use ledger for the final test interval."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError("path must be a Path")
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS campaign_final_use (
                  dataset_id TEXT NOT NULL,
                  split_id TEXT NOT NULL,
                  reservation_token TEXT NOT NULL UNIQUE,
                  survivor_ids_json TEXT NOT NULL,
                  proposal_id TEXT,
                  evidence_sha256 TEXT,
                  consumed_at TEXT,
                  PRIMARY KEY (dataset_id, split_id)
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0, isolation_level=None)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _token(dataset_id: str, split_id: str, survivors_json: str) -> str:
        payload = json.dumps(
            {
                "dataset_id": dataset_id,
                "split_id": split_id,
                "survivor_ids_json": survivors_json,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def reserve(
        self,
        *,
        dataset_id: str,
        split_id: str,
        survivor_ids: tuple[str, ...],
    ) -> str:
        dataset_id = _nonempty(dataset_id, name="dataset_id")
        split_id = _nonempty(split_id, name="split_id")
        survivors_json = json.dumps(_survivors(survivor_ids), separators=(",", ":"))
        token = self._token(dataset_id, split_id, survivors_json)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT reservation_token, survivor_ids_json, consumed_at
                    FROM campaign_final_use
                    WHERE dataset_id = ? AND split_id = ?
                    """,
                    (dataset_id, split_id),
                ).fetchone()
                if row is None:
                    connection.execute(
                        """
                        INSERT INTO campaign_final_use (
                          dataset_id, split_id, reservation_token, survivor_ids_json
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (dataset_id, split_id, token, survivors_json),
                    )
                elif row[0] == token and row[1] == survivors_json:
                    pass
                elif row[2] is not None:
                    raise FinalTestIsolationError("CAMPAIGN_FINAL_ALREADY_CONSUMED")
                else:
                    raise FinalTestIsolationError("CAMPAIGN_FINAL_RESERVATION_MISMATCH")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return token

    def consume(
        self,
        *,
        token: str,
        proposal_id: str,
        evidence_sha256: str,
    ) -> FinalConsumption:
        token = _sha256(token, name="token")
        proposal_id = _nonempty(proposal_id, name="proposal_id")
        evidence_sha256 = _sha256(evidence_sha256, name="evidence_sha256")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    """
                    SELECT proposal_id, evidence_sha256, consumed_at
                    FROM campaign_final_use WHERE reservation_token = ?
                    """,
                    (token,),
                ).fetchone()
                if row is None:
                    raise FinalTestIsolationError("CAMPAIGN_FINAL_TOKEN_INVALID")
                if row[2] is None:
                    consumed_at = datetime.now(UTC).isoformat()
                    connection.execute(
                        """
                        UPDATE campaign_final_use
                        SET proposal_id = ?, evidence_sha256 = ?, consumed_at = ?
                        WHERE reservation_token = ? AND consumed_at IS NULL
                        """,
                        (proposal_id, evidence_sha256, consumed_at, token),
                    )
                elif row[0] == proposal_id and row[1] == evidence_sha256:
                    consumed_at = str(row[2])
                else:
                    raise FinalTestIsolationError("CAMPAIGN_FINAL_ALREADY_CONSUMED")
                connection.commit()
            except BaseException:
                connection.rollback()
                raise
        return FinalConsumption(
            reservation_token=token,
            proposal_id=proposal_id,
            evidence_sha256=evidence_sha256,
            consumed_at=consumed_at,
        )
