-- Anonymous workspaces and per-module analysis history.
CREATE TABLE workspaces (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);

CREATE TABLE analysis_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    module TEXT NOT NULL,
    inputs_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX analysis_records_latest ON analysis_records (workspace_id, module, id DESC);
