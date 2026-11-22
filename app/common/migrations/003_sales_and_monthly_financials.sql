-- Monthly menu sales (menu engineering) and monthly revenue/cost records (operating trend).
ALTER TABLE menus ADD COLUMN other_cost TEXT NOT NULL DEFAULT '0';   -- per-unit packaging etc.

CREATE TABLE menu_sales (
    menu_id INTEGER NOT NULL REFERENCES menus(id) ON DELETE CASCADE,
    period TEXT NOT NULL,          -- YYYY-MM
    quantity TEXT NOT NULL,
    price TEXT NOT NULL,           -- average selling price that month
    PRIMARY KEY (menu_id, period)
);

CREATE TABLE monthly_financials (
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    period TEXT NOT NULL,          -- YYYY-MM
    revenue TEXT NOT NULL,
    rent TEXT NOT NULL,
    labor TEXT NOT NULL,
    material TEXT NOT NULL,
    utilities TEXT NOT NULL,
    advertising TEXT NOT NULL,
    other TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (workspace_id, period)
);
