BEGIN IMMEDIATE;

ALTER TABLE market_events
ADD COLUMN checkpoint_base_sequence INTEGER NOT NULL DEFAULT 0
CHECK (checkpoint_base_sequence >= 0);

ALTER TABLE order_events
ADD COLUMN checkpoint_sequence INTEGER NOT NULL DEFAULT 1
CHECK (checkpoint_sequence >= 1);

ALTER TABLE position_snapshots
ADD COLUMN checkpoint_base_sequence INTEGER NOT NULL DEFAULT 0
CHECK (checkpoint_base_sequence >= 0);

COMMIT;
