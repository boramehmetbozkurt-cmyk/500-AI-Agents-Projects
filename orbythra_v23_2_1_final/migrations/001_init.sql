-- ORBYTHRA schema v1. Compatible with PostgreSQL and SQLite.
CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_workspace_created ON audit_events(workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS evidence_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    workspace_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    label TEXT,
    evidence_json TEXT NOT NULL,
    created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_workspace_created ON evidence_snapshots(workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS pilot_runs (
    run_id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    workspace_id TEXT NOT NULL,
    principal_id TEXT NOT NULL,
    request_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pilot_workspace_created ON pilot_runs(workspace_id, created_at DESC);
