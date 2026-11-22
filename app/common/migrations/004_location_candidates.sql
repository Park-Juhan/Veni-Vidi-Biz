-- Saved location candidates for property comparison (any number per workspace).
CREATE TABLE location_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    rent TEXT NOT NULL,
    deposit TEXT NOT NULL,
    area TEXT NOT NULL,
    interior TEXT NOT NULL,
    fit TEXT NOT NULL,             -- self-rated 1..5
    traffic TEXT NOT NULL,         -- self-rated 1..5
    facility TEXT NOT NULL,        -- self-rated 1..5
    region_code TEXT,              -- reserved for public commercial-area data (step 6)
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (workspace_id, name)
);
