BEGIN IMMEDIATE;

DROP TRIGGER IF EXISTS registry_events_append_only_update;
DROP TRIGGER IF EXISTS registry_events_append_only_delete;
DROP TRIGGER IF EXISTS current_state_requires_initial_event;
DROP TRIGGER IF EXISTS current_state_update_requires_event;
DROP TRIGGER IF EXISTS current_state_cannot_be_deleted;
DROP INDEX IF EXISTS idx_registry_events_strategy_sequence;

ALTER TABLE registry_events RENAME TO registry_events_v1;
ALTER TABLE strategy_current_state RENAME TO strategy_current_state_v1;

CREATE TABLE registry_events (
    sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL UNIQUE,
    idempotency_payload_sha256 TEXT NOT NULL CHECK (
        length(idempotency_payload_sha256) = 64
        AND idempotency_payload_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    strategy_id TEXT NOT NULL,
    from_state TEXT CHECK (
        from_state IS NULL OR from_state IN (
            'generated', 'backtested', 'validated', 'candidate', 'paper_shadow',
            'paper_observing', 'paper_ranked', 'leader', 'review',
            'rejected', 'paused', 'retired'
        )
    ),
    to_state TEXT NOT NULL CHECK (
        to_state IN (
            'generated', 'backtested', 'validated', 'candidate', 'paper_shadow',
            'paper_observing', 'paper_ranked', 'leader', 'review',
            'rejected', 'paused', 'retired'
        )
    ),
    actor TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    immutable_refs_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    FOREIGN KEY (strategy_id) REFERENCES strategy_definitions(strategy_id)
) STRICT;

INSERT INTO registry_events SELECT * FROM registry_events_v1;

CREATE TABLE strategy_current_state (
    strategy_id TEXT PRIMARY KEY,
    current_state TEXT NOT NULL CHECK (
        current_state IN (
            'generated', 'backtested', 'validated', 'candidate', 'paper_shadow',
            'paper_observing', 'paper_ranked', 'leader', 'review',
            'rejected', 'paused', 'retired'
        )
    ),
    last_event_id TEXT NOT NULL UNIQUE,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (strategy_id) REFERENCES strategy_definitions(strategy_id),
    FOREIGN KEY (last_event_id) REFERENCES registry_events(event_id)
) STRICT;

INSERT INTO strategy_current_state SELECT * FROM strategy_current_state_v1;
DROP TABLE strategy_current_state_v1;
DROP TABLE registry_events_v1;

CREATE INDEX idx_registry_events_strategy_sequence
ON registry_events(strategy_id, sequence_no);

CREATE TRIGGER registry_events_append_only_update
BEFORE UPDATE ON registry_events BEGIN
    SELECT RAISE(ABORT, 'APPEND_ONLY_REGISTRY_EVENTS');
END;
CREATE TRIGGER registry_events_append_only_delete
BEFORE DELETE ON registry_events BEGIN
    SELECT RAISE(ABORT, 'APPEND_ONLY_REGISTRY_EVENTS');
END;
CREATE TRIGGER current_state_requires_initial_event
BEFORE INSERT ON strategy_current_state
WHEN NOT EXISTS (
    SELECT 1 FROM registry_events AS event
    WHERE event.event_id = NEW.last_event_id
      AND event.strategy_id = NEW.strategy_id
      AND event.from_state IS NULL
      AND event.to_state = NEW.current_state
      AND event.occurred_at = NEW.updated_at
) BEGIN
    SELECT RAISE(ABORT, 'DERIVED_STATE_REQUIRES_MATCHING_EVENT');
END;
CREATE TRIGGER current_state_update_requires_event
BEFORE UPDATE ON strategy_current_state
WHEN NOT EXISTS (
    SELECT 1 FROM registry_events AS event
    WHERE event.event_id = NEW.last_event_id
      AND event.strategy_id = NEW.strategy_id
      AND event.from_state = OLD.current_state
      AND event.to_state = NEW.current_state
      AND event.occurred_at = NEW.updated_at
) BEGIN
    SELECT RAISE(ABORT, 'DERIVED_STATE_REQUIRES_MATCHING_EVENT');
END;
CREATE TRIGGER current_state_cannot_be_deleted
BEFORE DELETE ON strategy_current_state BEGIN
    SELECT RAISE(ABORT, 'DERIVED_STATE_CANNOT_BE_DELETED');
END;

COMMIT;
