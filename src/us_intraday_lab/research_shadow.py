"""Append-only research-shadow evidence with no broker execution capability."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ResearchShadowStatus:
    campaign_id: str
    observed_sessions: int
    minimum_sessions: int
    forward_gate_eligible: bool
    order_route: str


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class ResearchShadowStore:
    """Store prospective observations without importing or exposing a broker."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path):
            raise TypeError("path must be a Path")
        self.path = path.resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS research_shadow_campaigns (
                  campaign_id TEXT PRIMARY KEY,
                  proposal_sha256 TEXT NOT NULL,
                  selection_sha256 TEXT NOT NULL,
                  winner_id TEXT NOT NULL,
                  parameters_json TEXT NOT NULL,
                  start_session_not_before TEXT NOT NULL,
                  minimum_sessions INTEGER NOT NULL,
                  order_route TEXT NOT NULL CHECK (order_route = 'FORBIDDEN'),
                  created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS research_shadow_observations (
                  campaign_id TEXT NOT NULL,
                  session_date TEXT NOT NULL,
                  observation_json TEXT NOT NULL,
                  content_sha256 TEXT NOT NULL,
                  recorded_at TEXT NOT NULL,
                  PRIMARY KEY (campaign_id, session_date),
                  FOREIGN KEY (campaign_id) REFERENCES research_shadow_campaigns(campaign_id)
                );
                CREATE TRIGGER IF NOT EXISTS research_shadow_campaigns_no_update
                BEFORE UPDATE ON research_shadow_campaigns
                BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_RESEARCH_SHADOW_CAMPAIGNS'); END;
                CREATE TRIGGER IF NOT EXISTS research_shadow_campaigns_no_delete
                BEFORE DELETE ON research_shadow_campaigns
                BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_RESEARCH_SHADOW_CAMPAIGNS'); END;
                CREATE TRIGGER IF NOT EXISTS research_shadow_observations_no_update
                BEFORE UPDATE ON research_shadow_observations
                BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_RESEARCH_SHADOW_OBSERVATIONS'); END;
                CREATE TRIGGER IF NOT EXISTS research_shadow_observations_no_delete
                BEFORE DELETE ON research_shadow_observations
                BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_RESEARCH_SHADOW_OBSERVATIONS'); END;
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def start_campaign(
        self,
        *,
        proposal_sha256: str,
        selection_sha256: str,
        winner_id: str,
        parameters: dict[str, object],
        start_session_not_before: date,
        minimum_sessions: int,
        created_at: datetime,
    ) -> str:
        if minimum_sessions < 120:
            raise ValueError("research shadow requires at least 120 prospective sessions")
        if any(len(value) != 64 for value in (proposal_sha256, selection_sha256)):
            raise ValueError("research shadow hashes must be SHA-256 digests")
        payload = {
            "proposal_sha256": proposal_sha256,
            "selection_sha256": selection_sha256,
            "winner_id": winner_id,
            "parameters": parameters,
            "start_session_not_before": start_session_not_before.isoformat(),
            "minimum_sessions": minimum_sessions,
            "order_route": "FORBIDDEN",
        }
        campaign_id = "research-shadow-" + _sha256(_canonical_json(payload))[:32]
        row = (
            campaign_id,
            proposal_sha256,
            selection_sha256,
            winner_id,
            _canonical_json(parameters),
            start_session_not_before.isoformat(),
            minimum_sessions,
            "FORBIDDEN",
            created_at.isoformat(),
        )
        with self._connect() as connection:
            existing = connection.execute(
                "SELECT * FROM research_shadow_campaigns WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO research_shadow_campaigns VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )
            elif existing[:-1] != row[:-1]:
                raise ValueError("research shadow campaign identity was reused with drift")
        return campaign_id

    def record_observation(
        self,
        *,
        campaign_id: str,
        session_date: date,
        observation: dict[str, object],
        recorded_at: datetime,
    ) -> str:
        if any(key.lower().find("order") >= 0 for key in observation):
            raise ValueError("research shadow observations cannot contain order fields")
        content = _canonical_json(observation)
        digest = _sha256(content)
        with self._connect() as connection:
            campaign = connection.execute(
                """
                SELECT start_session_not_before FROM research_shadow_campaigns
                WHERE campaign_id = ?
                """,
                (campaign_id,),
            ).fetchone()
            if campaign is None:
                raise ValueError("research shadow campaign does not exist")
            if session_date < date.fromisoformat(campaign[0]):
                raise ValueError("observation predates the prospective campaign boundary")
            existing = connection.execute(
                """
                SELECT observation_json, content_sha256
                FROM research_shadow_observations
                WHERE campaign_id = ? AND session_date = ?
                """,
                (campaign_id, session_date.isoformat()),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO research_shadow_observations VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        campaign_id,
                        session_date.isoformat(),
                        content,
                        digest,
                        recorded_at.isoformat(),
                    ),
                )
            elif existing != (content, digest):
                raise ValueError("research shadow observation is append-only")
        return digest

    def status(self, campaign_id: str) -> ResearchShadowStatus:
        with self._connect() as connection:
            campaign = connection.execute(
                """
                SELECT minimum_sessions, order_route FROM research_shadow_campaigns
                WHERE campaign_id = ?
                """,
                (campaign_id,),
            ).fetchone()
            if campaign is None:
                raise ValueError("research shadow campaign does not exist")
            count = int(
                connection.execute(
                    """
                    SELECT count(*) FROM research_shadow_observations WHERE campaign_id = ?
                    """,
                    (campaign_id,),
                ).fetchone()[0]
            )
        minimum_sessions = int(campaign[0])
        return ResearchShadowStatus(
            campaign_id=campaign_id,
            observed_sessions=count,
            minimum_sessions=minimum_sessions,
            forward_gate_eligible=count >= minimum_sessions,
            order_route=str(campaign[1]),
        )
