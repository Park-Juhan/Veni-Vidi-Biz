-- Promotion campaigns actually run, with cost and observed results (blank = not measured).
CREATE TABLE campaigns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    channel TEXT NOT NULL,
    owner TEXT NOT NULL,              -- 직접 / 외부 업체
    started_on TEXT NOT NULL,         -- YYYY-MM-DD
    ended_on TEXT NOT NULL,
    cost TEXT NOT NULL,
    hours_per_week TEXT NOT NULL,
    new_customers TEXT,
    revenue_before TEXT,              -- revenue in a same-length period before the campaign
    revenue_after TEXT,               -- revenue during the campaign
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX campaigns_by_workspace ON campaigns (workspace_id, started_on DESC);
