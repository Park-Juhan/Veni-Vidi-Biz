-- 한국부동산원 「상업용부동산 임대동향조사」 상권별 소규모 상가 임대료 (서울 주요 상권, 천원/㎡ · 월).
CREATE TABLE area_rents (
    zone TEXT NOT NULL,              -- 도심지역, 강남지역 ... ('소계' rows: zone or Seoul averages)
    area TEXT NOT NULL,              -- 망원역, 홍대/합정 ... or 소계
    quarter TEXT NOT NULL,           -- 2026.2/4
    rent_per_m2 REAL NOT NULL,       -- 천원/㎡ (월)
    PRIMARY KEY (zone, area)
);

-- Dishes analysed in the material cost module (02): standard recipe scaled to the planned volume.
CREATE TABLE dishes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workspace_id TEXT NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    monthly_volume TEXT NOT NULL,    -- 월 예상 판매량 (Decimal text)
    cost TEXT NOT NULL,              -- 1인분 재료비 (Decimal text)
    items TEXT NOT NULL,             -- JSON: [{name, quantity, unit, cost}]
    updated_at TEXT NOT NULL,
    UNIQUE (workspace_id, name)
);

CREATE INDEX area_counts_by_period ON area_counts (period);
