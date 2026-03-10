CREATE TABLE world_snapshots (
    tick INTEGER PRIMARY KEY,
    state_json TEXT NOT NULL,
    seed INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE events (
    id TEXT PRIMARY KEY,
    tick_created INTEGER NOT NULL,
    resolved INTEGER NOT NULL CHECK (resolved IN (0, 1)),
    state_json TEXT NOT NULL
);

CREATE TABLE facts (
    fact_id TEXT PRIMARY KEY,
    tick INTEGER NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE TABLE beliefs (
    character_id TEXT NOT NULL,
    belief_id TEXT NOT NULL,
    tick INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (character_id, belief_id)
);

CREATE TABLE action_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tick INTEGER NOT NULL,
    character_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    verdict TEXT NOT NULL,
    retry_count INTEGER NOT NULL,
    is_fallback INTEGER NOT NULL CHECK (is_fallback IN (0, 1)),
    fallback_reason TEXT,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE checkpoints (
    tick INTEGER PRIMARY KEY,
    world_snapshot BLOB NOT NULL,
    rng_state BLOB NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
