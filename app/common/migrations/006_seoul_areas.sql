-- External reference data: Seoul commercial-area statistics (서울시 상권분석서비스, 상권 단위).
-- Loaded by import_data.py from CSV files; not tied to any workspace. Counts and won amounts are whole numbers.
CREATE TABLE datasets (
    name TEXT PRIMARY KEY,           -- e.g. 추정매출-상권
    provider TEXT NOT NULL,
    file_name TEXT NOT NULL,
    period_from TEXT,                -- YYYYQ, e.g. 20251
    period_to TEXT,
    row_count INTEGER NOT NULL,
    imported_at TEXT NOT NULL
);
CREATE TABLE areas (
    code TEXT PRIMARY KEY,           -- 상권_코드
    name TEXT NOT NULL,
    kind TEXT NOT NULL,              -- 골목상권 / 발달상권 / 전통시장 / 관광특구
    district TEXT NOT NULL,          -- 자치구
    dong TEXT NOT NULL,              -- 행정동
    x INTEGER,                       -- source coordinates (TM), kept for later map use
    y INTEGER,
    size INTEGER                     -- 영역 면적 (㎡)
);
CREATE TABLE area_sales (
    area_code TEXT NOT NULL,
    period TEXT NOT NULL,
    industry_code TEXT NOT NULL,
    industry TEXT NOT NULL,
    amount INTEGER NOT NULL,         -- 당월_매출_금액
    count INTEGER NOT NULL,          -- 당월_매출_건수
    weekend_amount INTEGER NOT NULL,
    time_00_06 INTEGER NOT NULL, time_06_11 INTEGER NOT NULL, time_11_14 INTEGER NOT NULL,
    time_14_17 INTEGER NOT NULL, time_17_21 INTEGER NOT NULL, time_21_24 INTEGER NOT NULL,
    male_amount INTEGER NOT NULL, female_amount INTEGER NOT NULL,
    age_10 INTEGER NOT NULL, age_20 INTEGER NOT NULL, age_30 INTEGER NOT NULL,
    age_40 INTEGER NOT NULL, age_50 INTEGER NOT NULL, age_60 INTEGER NOT NULL,
    PRIMARY KEY (area_code, period, industry_code)
);
CREATE INDEX area_sales_by_industry ON area_sales (industry, period);
CREATE TABLE area_stores (
    area_code TEXT NOT NULL,
    period TEXT NOT NULL,
    industry_code TEXT NOT NULL,
    industry TEXT NOT NULL,
    stores INTEGER NOT NULL,
    franchise INTEGER NOT NULL,
    open_rate INTEGER NOT NULL,      -- percent, as published
    opened INTEGER NOT NULL,
    close_rate INTEGER NOT NULL,
    closed INTEGER NOT NULL,
    PRIMARY KEY (area_code, period, industry_code)
);
-- One number per area and quarter: footfall, residents, households, workers, facilities ...
CREATE TABLE area_counts (
    area_code TEXT NOT NULL,
    period TEXT NOT NULL,
    metric TEXT NOT NULL,
    value INTEGER NOT NULL,
    dataset TEXT NOT NULL,           -- datasets.name; re-importing a file replaces its rows
    PRIMARY KEY (area_code, period, metric)
);
CREATE TABLE area_change (
    area_code TEXT NOT NULL,
    period TEXT NOT NULL,
    indicator TEXT NOT NULL,         -- HH / HL / LH / LL
    indicator_name TEXT NOT NULL,    -- 정체 / 상권축소 / 상권확장 / 다이나믹
    operating_months INTEGER,
    closed_months INTEGER,
    seoul_operating_months INTEGER,
    seoul_closed_months INTEGER,
    PRIMARY KEY (area_code, period)
);
