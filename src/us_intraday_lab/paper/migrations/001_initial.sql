BEGIN IMMEDIATE;

CREATE TABLE IF NOT EXISTS paper_sessions (
    paper_session_id TEXT PRIMARY KEY,
    session_date TEXT NOT NULL,
    status TEXT NOT NULL CHECK (
        status IN ('initializing', 'running', 'closeout', 'closed', 'blocked')
    ),
    session_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (
        length(content_sha256) = 64
        AND content_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS market_events (
    sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_event_id TEXT NOT NULL UNIQUE,
    paper_session_id TEXT NOT NULL,
    symbol TEXT NOT NULL CHECK (symbol IN ('SPY', 'QQQ', 'IWM')),
    available_at TEXT NOT NULL,
    event_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (
        length(content_sha256) = 64
        AND content_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    FOREIGN KEY (paper_session_id) REFERENCES paper_sessions(paper_session_id)
) STRICT;

CREATE TABLE IF NOT EXISTS order_intents (
    sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
    idempotency_key TEXT NOT NULL UNIQUE,
    paper_session_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    symbol TEXT NOT NULL CHECK (symbol IN ('SPY', 'QQQ', 'IWM')),
    intent_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (
        length(content_sha256) = 64
        AND content_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL,
    FOREIGN KEY (paper_session_id) REFERENCES paper_sessions(paper_session_id)
) STRICT;

CREATE TABLE IF NOT EXISTS order_events (
    sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
    order_event_id TEXT NOT NULL UNIQUE,
    paper_session_id TEXT NOT NULL,
    broker_order_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL,
    event_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (
        length(content_sha256) = 64
        AND content_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    occurred_at TEXT NOT NULL,
    FOREIGN KEY (paper_session_id) REFERENCES paper_sessions(paper_session_id),
    FOREIGN KEY (idempotency_key) REFERENCES order_intents(idempotency_key)
) STRICT;

CREATE TABLE IF NOT EXISTS position_snapshots (
    sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT NOT NULL UNIQUE,
    paper_session_id TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (
        length(content_sha256) = 64
        AND content_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    observed_at TEXT NOT NULL,
    FOREIGN KEY (paper_session_id) REFERENCES paper_sessions(paper_session_id)
) STRICT;

CREATE TABLE IF NOT EXISTS risk_decisions (
    sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT NOT NULL UNIQUE,
    idempotency_key TEXT NOT NULL UNIQUE,
    paper_session_id TEXT NOT NULL,
    approved INTEGER NOT NULL CHECK (approved IN (0, 1)),
    reason_code TEXT NOT NULL,
    decision_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (
        length(content_sha256) = 64
        AND content_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    decided_at TEXT NOT NULL,
    FOREIGN KEY (paper_session_id) REFERENCES paper_sessions(paper_session_id),
    FOREIGN KEY (idempotency_key) REFERENCES order_intents(idempotency_key)
) STRICT;

CREATE TABLE IF NOT EXISTS strategy_session_state (
    paper_session_id TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    state_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (
        length(content_sha256) = 64
        AND content_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    updated_at TEXT NOT NULL,
    PRIMARY KEY (paper_session_id, strategy_id),
    FOREIGN KEY (paper_session_id) REFERENCES paper_sessions(paper_session_id)
) STRICT;

CREATE TABLE IF NOT EXISTS paper_checkpoints (
    sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
    checkpoint_id TEXT NOT NULL UNIQUE,
    paper_session_id TEXT NOT NULL,
    event_sequence INTEGER NOT NULL CHECK (event_sequence >= 0),
    checkpoint_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (
        length(content_sha256) = 64
        AND content_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    created_at TEXT NOT NULL,
    UNIQUE (paper_session_id, event_sequence),
    FOREIGN KEY (paper_session_id) REFERENCES paper_sessions(paper_session_id)
) STRICT;

CREATE TABLE IF NOT EXISTS reconciliation_runs (
    sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
    reconciliation_id TEXT NOT NULL UNIQUE,
    paper_session_id TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('clean', 'recoverable', 'blocked')),
    reconciliation_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (
        length(content_sha256) = 64
        AND content_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    completed_at TEXT NOT NULL,
    FOREIGN KEY (paper_session_id) REFERENCES paper_sessions(paper_session_id)
) STRICT;

CREATE TABLE IF NOT EXISTS incident_events (
    sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id TEXT NOT NULL UNIQUE,
    paper_session_id TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'critical')),
    reason_code TEXT NOT NULL,
    event_json TEXT NOT NULL,
    content_sha256 TEXT NOT NULL CHECK (
        length(content_sha256) = 64
        AND content_sha256 NOT GLOB '*[^0-9a-f]*'
    ),
    occurred_at TEXT NOT NULL,
    FOREIGN KEY (paper_session_id) REFERENCES paper_sessions(paper_session_id)
) STRICT;

CREATE INDEX IF NOT EXISTS idx_market_events_session_sequence
ON market_events(paper_session_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_order_events_session_sequence
ON order_events(paper_session_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_position_snapshots_session_sequence
ON position_snapshots(paper_session_id, sequence_no);
CREATE INDEX IF NOT EXISTS idx_checkpoints_session_sequence
ON paper_checkpoints(paper_session_id, event_sequence);

CREATE TRIGGER IF NOT EXISTS market_events_append_only_update
BEFORE UPDATE ON market_events BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_MARKET_EVENTS'); END;
CREATE TRIGGER IF NOT EXISTS market_events_append_only_delete
BEFORE DELETE ON market_events BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_MARKET_EVENTS'); END;
CREATE TRIGGER IF NOT EXISTS order_intents_append_only_update
BEFORE UPDATE ON order_intents BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_ORDER_INTENTS'); END;
CREATE TRIGGER IF NOT EXISTS order_intents_append_only_delete
BEFORE DELETE ON order_intents BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_ORDER_INTENTS'); END;
CREATE TRIGGER IF NOT EXISTS order_events_append_only_update
BEFORE UPDATE ON order_events BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_ORDER_EVENTS'); END;
CREATE TRIGGER IF NOT EXISTS order_events_append_only_delete
BEFORE DELETE ON order_events BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_ORDER_EVENTS'); END;
CREATE TRIGGER IF NOT EXISTS position_snapshots_append_only_update
BEFORE UPDATE ON position_snapshots BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_POSITION_SNAPSHOTS'); END;
CREATE TRIGGER IF NOT EXISTS position_snapshots_append_only_delete
BEFORE DELETE ON position_snapshots BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_POSITION_SNAPSHOTS'); END;
CREATE TRIGGER IF NOT EXISTS risk_decisions_append_only_update
BEFORE UPDATE ON risk_decisions BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_RISK_DECISIONS'); END;
CREATE TRIGGER IF NOT EXISTS risk_decisions_append_only_delete
BEFORE DELETE ON risk_decisions BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_RISK_DECISIONS'); END;
CREATE TRIGGER IF NOT EXISTS paper_checkpoints_append_only_update
BEFORE UPDATE ON paper_checkpoints BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_PAPER_CHECKPOINTS'); END;
CREATE TRIGGER IF NOT EXISTS paper_checkpoints_append_only_delete
BEFORE DELETE ON paper_checkpoints BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_PAPER_CHECKPOINTS'); END;
CREATE TRIGGER IF NOT EXISTS reconciliation_runs_append_only_update
BEFORE UPDATE ON reconciliation_runs BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_RECONCILIATION_RUNS'); END;
CREATE TRIGGER IF NOT EXISTS reconciliation_runs_append_only_delete
BEFORE DELETE ON reconciliation_runs BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_RECONCILIATION_RUNS'); END;
CREATE TRIGGER IF NOT EXISTS incident_events_append_only_update
BEFORE UPDATE ON incident_events BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_INCIDENT_EVENTS'); END;
CREATE TRIGGER IF NOT EXISTS incident_events_append_only_delete
BEFORE DELETE ON incident_events BEGIN SELECT RAISE(ABORT, 'APPEND_ONLY_INCIDENT_EVENTS'); END;

COMMIT;
