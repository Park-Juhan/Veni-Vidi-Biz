-- Materials with purchase history, menus and their recipes. Amounts are TEXT (exact Decimal).
CREATE TABLE materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    unit TEXT NOT NULL,            -- purchase unit: kg, g, L, mL, 개
    yield_rate TEXT NOT NULL,      -- usable share in percent, 1..100
    created_at TEXT NOT NULL,
    UNIQUE (workspace_id, name)
);

CREATE TABLE material_purchases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    quantity TEXT NOT NULL,        -- in materials.unit
    unit_price TEXT NOT NULL,      -- won per one purchase unit
    purchased_at TEXT NOT NULL
);
CREATE INDEX material_purchases_latest ON material_purchases (material_id, id DESC);

CREATE TABLE menus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (workspace_id, name)
);

CREATE TABLE recipe_items (
    menu_id INTEGER NOT NULL REFERENCES menus(id) ON DELETE CASCADE,
    material_id INTEGER NOT NULL REFERENCES materials(id) ON DELETE CASCADE,
    quantity TEXT NOT NULL,
    unit TEXT NOT NULL,            -- usage unit, same dimension as the material
    position INTEGER NOT NULL,
    PRIMARY KEY (menu_id, material_id)
);
